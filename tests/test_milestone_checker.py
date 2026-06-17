"""Milestone checker tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.db.meta import set_meta
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions, load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter
from core.stats.models import BoxscoreData, GameMeta, PitcherLine
from core.stats.pitching_special import detect_special_game

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "test.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones() -> MilestoneDefinitions:
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones: MilestoneDefinitions) -> MilestoneChecker:
    return MilestoneChecker(aggregator, milestones, season_games_total=162)


def _import_games(aggregator: Aggregator, *names: str, season: int = 2026) -> list[int]:
    imported: list[int] = []
    for name in names:
        data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
        result = aggregator.import_boxscore(data, season=season)
        assert result.error is None
        imported.append(data.meta.game_id)
    return imported


def test_load_milestones_csv_grade(milestones: MilestoneDefinitions) -> None:
    perfect = milestones.get_by_key("pit_game_perfect_game")
    assert perfect is not None
    assert perfect.grade == "legendary"
    cg = milestones.get_by_key("pit_game_cg")
    assert cg is not None
    assert cg.grade == "uncommon"
    assert len(milestones.all_milestones) == 276
    ratio_keys = {
        item.key for item in milestones.all_milestones if item.scope == "season_ratio"
    }
    assert ratio_keys == set()


def test_game_scope_multi_hr_not_triggered_on_single_hr(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    game_ids = _import_games(aggregator, "game_box_13.html")
    achievements = checker.check_new_games(game_ids, season=2026)
    hr2 = [item for item in achievements if item.milestone.key == "bat_game_hr_2"]
    assert hr2 == []


def test_game_scope_multi_hr_triggered(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    if not (SAMPLES_BOX / "game_box_20.html").is_file():
        pytest.skip("game_box_20 sample missing")
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
    data.home_batting_notes = re.sub(
        r"K\. Tucker\s*\n\s*\(2, 5th Inning off R\. Nelson, 0 on, 0 outs\)",
        "K. Tucker 2 (5, 5th Inning off R. Nelson, 0 on, 0 outs)",
        data.home_batting_notes,
    )
    result = aggregator.import_boxscore(data, season=2026)
    assert result.error is None
    achievements = checker.check_new_games([data.meta.game_id], season=2026)
    hr2 = [item for item in achievements if item.milestone.key == "bat_game_hr_2"]
    assert len(hr2) >= 1
    assert any(item.player_name == "K. Tucker" for item in hr2)


def test_check_new_games_respects_tracked_teams(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html")
    all_checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    giants_checker = MilestoneChecker(
        aggregator,
        milestones,
        season_games_total=162,
        tracked_teams=["SF"],
    )
    all_achievements = all_checker.check_new_games(game_ids, season=2026)
    giants_achievements = giants_checker.check_new_games(game_ids, season=2026)

    giants_players = {item.player_id for item in giants_achievements if item.player_id}
    assert giants_players

    career500_all = [
        item for item in all_achievements if item.milestone.key == "bat_career_hr_500"
    ]
    career500_giants = [
        item for item in giants_achievements if item.milestone.key == "bat_career_hr_500"
    ]
    assert career500_all
    assert career500_giants == []


def test_career_scope_with_initial_stats(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html")
    achievements = checker.check_new_games(game_ids, season=2026)
    career500 = [item for item in achievements if item.milestone.key == "bat_career_hr_500"]
    assert len(career500) == 1
    assert career500[0].player_id == 28987


def test_no_duplicate_career_record(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html", "game_box_14.html")
    first = checker.check_new_games([game_ids[0]], season=2026)
    checker.record_achievements(first)
    second = checker.check_new_games([game_ids[1]], season=2026)
    checker.record_achievements(second)
    rows = aggregator.conn.execute(
        """
        SELECT COUNT(*) AS cnt FROM milestone_records
        WHERE player_id = ? AND milestone_key = 'bat_career_hr_500'
        """,
        (28987,),
    ).fetchone()
    assert rows["cnt"] == 1


def test_complete_game_detection() -> None:
    meta = GameMeta(
        game_id=1,
        date="2026-04-01",
        away_team="Away",
        home_team="Home",
        away_score=0,
        home_score=1,
        away_hits=0,
        home_hits=5,
        away_errors=0,
        home_errors=0,
    )
    pitcher = PitcherLine(
        player_name="A. Pitcher",
        player_id=1,
        team="Home",
        decision="W",
        decision_record="(1-0)",
        ip=9.0,
        h=0,
        r=0,
        er=0,
        bb=0,
        k=10,
        hr=0,
        bf=27,
        pi=100,
        era=0.0,
    )
    data = BoxscoreData(
        meta=meta,
        away_batting=[],
        home_batting=[],
        away_pitching=[],
        home_pitching=[pitcher],
        away_batting_notes="",
        home_batting_notes="",
    )
    flags = detect_special_game(pitcher, [pitcher], meta, "Home", data)
    assert flags["is_cg"] == 1
    assert flags["is_sho"] == 1
    assert flags["is_no_hitter"] == 1
    assert flags["is_perfect_game"] == 1


def test_ratio_milestone_qualifier(aggregator: Aggregator) -> None:
    defs = MilestoneDefinitions(
        batting=[
            MilestoneDefinition(
                key="season_avg_400",
                label="시즌 4할",
                stat="season_avg",
                threshold=0.4,
                scope="season_ratio",
                category="batting",
            )
        ],
        pitching=[],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        """
        INSERT INTO players (player_id, full_name, short_name) VALUES (1, 'Test Player', 'T. Player')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (1, '2026-04-01', 2026, 'A', 'H', 1, 2, '[]', '[]')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, season_hr, season_rbi
        ) VALUES (1, 1, 2026, 'H', '2026-04-01', 400, 200, 0, 0)
        """
    )
    achievements = checker.check_season_ratios(2026)
    assert achievements == []

    aggregator.conn.execute(
        "UPDATE batting_logs SET ab = 502, h = 201 WHERE player_id = 1 AND game_id = 1"
    )
    achievements = checker.check_season_ratios(2026)
    assert len(achievements) == 1
    assert achievements[0].current_value >= 0.4


def test_lower_direction_era(aggregator: Aggregator) -> None:
    defs = MilestoneDefinitions(
        batting=[],
        pitching=[
            MilestoneDefinition(
                key="season_era_200",
                label="시즌 2점대 ERA",
                stat="season_era",
                threshold=2.99,
                scope="season_ratio",
                category="pitching",
                direction="lower",
            )
        ],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (9, 'P Test', 'P. Test')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (9, '2026-04-01', 2026, 'A', 'H', 1, 2, '[]', '[]')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, er
        ) VALUES (9, 9, 2026, 'H', '2026-04-01', 486, 45)
        """
    )
    good = checker.check_season_ratios(2026)
    assert len(good) == 1

    aggregator.conn.execute(
        "UPDATE pitching_logs SET er = 60 WHERE player_id = 9 AND game_id = 9"
    )
    bad = checker.check_season_ratios(2026)
    assert bad == []


def test_career_first_stats_from_zero(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    aggregator.conn.executemany(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (?, ?, ?)",
        [(9001, "Rookie Batter", "R. Batter"), (9002, "Rookie Pitcher", "R. Pitcher")],
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (900, '2026-04-01', 2026, 'Away', 'Home', 2, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, home_runs, stolen_bases
        ) VALUES (900, 9001, 2026, 'Home', '2026-04-01', 4, 1, 1, 0, 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, h, bb, k, er,
            win, loss, save, hold, is_cg, is_sho, is_no_hitter, is_perfect_game
        ) VALUES (900, 9002, 2026, 'Home', '2026-04-01', 3, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([900], season=2026)
    batter_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9001
    }
    pitcher_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9002
    }

    assert {
        "bat_career_first_games",
        "bat_career_first_hit",
        "bat_career_first_rbi",
        "bat_career_first_sb",
    } <= batter_keys
    assert {
        "pit_career_first_game",
        "pit_career_first_k",
        "pit_career_first_hold",
        "pit_career_first_save",
    } <= pitcher_keys
    assert "pit_career_first_win" not in pitcher_keys


def test_career_first_stat_not_retriggered_with_prior_init(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (9003, 'Vet', 'V. Vet')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO career_batting_init (
            player_id, season, g, ab, h, hr, rbi, bb, k, doubles, triples, sb, r
        ) VALUES (9003, 2025, 10, 30, 5, 0, 2, 1, 8, 1, 0, 0, 1)
        """
    )
    set_meta(aggregator.conn, "init_season_coverage", "2025")
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (901, '2026-04-02', 2026, 'Away', 'Home', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, home_runs, stolen_bases
        ) VALUES (901, 9003, 2026, 'Home', '2026-04-02', 3, 1, 0, 0, 0)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([901], season=2026)
    first_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9003 and item.milestone.key.startswith("bat_career_first_")
    }
    assert first_keys == set()

