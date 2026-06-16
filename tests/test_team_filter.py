"""Team abbreviation resolution for tracked-team filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.definitions import load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    MLB_TEAM_ALIASES,
    build_tracked_team_match_sql,
    discover_mlb_teams_from_rows,
    expand_tracked_teams,
    find_unknown_mlb_teams,
    franchise_name_matches_known,
    is_ootp_mlb_league_row,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


def test_canonical_mlb_has_30_teams() -> None:
    assert len(CANONICAL_MLB_TEAMS) == 30


def test_find_unknown_mlb_teams() -> None:
    known = {**CANONICAL_MLB_TEAMS, **MLB_TEAM_ALIASES}
    unknown = find_unknown_mlb_teams(
        {"SF": "San Francisco Giants", "SY": "Seoul Yukies"},
        known,
    )
    assert "SF" not in unknown
    assert unknown == {"SY": "Seoul Yukies"}


def test_ootp_export_aliases_are_not_unknown_franchises() -> None:
    known = {**CANONICAL_MLB_TEAMS, **MLB_TEAM_ALIASES}
    discovered = {"ATH": "Athletics", "AZ": "Arizona", "SF": "San Francisco"}
    unknown = find_unknown_mlb_teams(discovered, known)
    assert unknown == {}


def test_franchise_name_matches_known() -> None:
    known = CANONICAL_MLB_TEAMS
    assert franchise_name_matches_known("Athletics", known) is True
    assert franchise_name_matches_known("Arizona", known) is True
    assert franchise_name_matches_known("Seoul Yukies", known) is False


def test_is_ootp_mlb_league_row_excludes_wbc() -> None:
    assert is_ootp_mlb_league_row(
        {
            "split_id": 1,
            "league_level_id": 1,
            "league_abbr": "WBC",
            "league_name": "World Baseball Classic",
        }
    ) is False
    assert is_ootp_mlb_league_row(
        {
            "split_id": 1,
            "league_level_id": 1,
            "league_abbr": "MLB",
            "league_name": "Major League Baseball",
        }
    ) is True


def test_discover_mlb_teams_ignores_non_mlb_leagues() -> None:
    rows = [
        {
            "split_id": 1,
            "league_level_id": 1,
            "league_abbr": "MLB",
            "team_abbr": "SF",
            "team_name": "San Francisco",
        },
        {
            "split_id": 1,
            "league_level_id": 1,
            "league_abbr": "WBC",
            "team_abbr": "KOR",
            "team_name": "Korea",
        },
        {
            "split_id": 1,
            "league_level_id": 8,
            "league_abbr": "KBO",
            "team_abbr": "LOT",
            "team_name": "Lotte",
        },
    ]
    teams = discover_mlb_teams_from_rows(rows)
    assert teams == {"SF": "San Francisco"}


def test_expand_sf_to_giants() -> None:
    names = expand_tracked_teams(["SF"])
    assert "San Francisco Giants" in names
    assert "SF" in names


@pytest.fixture
def giants_game_db(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "teams.db"
    agg = Aggregator(db_path)
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    agg.import_boxscore(data, season=2026)
    return agg


def test_tracked_sf_matches_boxscore_team_name(giants_game_db: Aggregator) -> None:
    players = giants_game_db.get_tracked_players(["SF"])
    assert len(players) > 0


def test_build_tracked_team_match_sql_fuzzy_custom_name() -> None:
    clause, params = build_tracked_team_match_sql(
        ["SY"],
        {"SY": "Seoul Yukies"},
    )
    assert "LIKE" in clause
    assert "%seoul%" in params


def test_tracked_custom_sy_team_from_affiliations(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "custom.db")
    try:
        agg.upsert_player(90001, "Y. Player", "Yukies Player")
        agg.upsert_player_team_affiliations(
            [
                {
                    "player_id": 90001,
                    "season": 2026,
                    "team_abbr": "SY",
                    "team_name": "Seoul",
                }
            ]
        )
        agg.conn.execute(
            """
            INSERT INTO career_batting_init (
                player_id, season, g, pa, ab, h, doubles, triples, hr, rbi,
                r, sb, cs, bb, hbp, k, sh, sf, gdp
            ) VALUES (90001, 2026, 10, 40, 35, 12, 2, 0, 3, 8, 6, 1, 0, 4, 1, 7, 0, 0, 0)
            """
        )
        agg.conn.commit()

        players = agg.get_tracked_players(
            ["SY"],
            custom_teams={"SY": "Seoul Yukies"},
        )
        assert [p["player_id"] for p in players] == [90001]

        season = agg.get_batting_season(90001, 2026)
        assert season is not None
        assert season["hr"] == 3
        assert season["_source"] == "init"
    finally:
        agg.close()
