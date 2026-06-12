"""Team milestone detection and manual recording tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.team_milestone import (
    check_team_game_batting,
    check_team_game_pitching,
    get_team_wins,
)
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"
GIANTS = "San Francisco Giants"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "team.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones():
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def tracked_checker(aggregator: Aggregator, milestones) -> MilestoneChecker:
    return MilestoneChecker(
        aggregator,
        milestones,
        season_games_total=162,
        tracked_teams=[GIANTS],
    )


def _seed_game(
    aggregator: Aggregator,
    *,
    game_id: int = 100,
    home: str = GIANTS,
    away: str = "New York Yankees",
    home_score: int = 5,
    away_score: int = 2,
) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (?, '2026-04-01', 2026, ?, ?, ?, ?, '[]', '[]', 1)
        """,
        (game_id, away, home, away_score, home_score),
    )
    aggregator.conn.commit()


def test_starter_all_hit_detection(aggregator: Aggregator) -> None:
    _seed_game(aggregator)
    for player_id, hits in ((1, 1), (2, 2), (3, 1)):
        aggregator.conn.execute(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, date, ab, h, rbi, is_substitute
            ) VALUES (100, ?, 2026, ?, '2026-04-01', 4, ?, 1, 0)
            """,
            (player_id, GIANTS, hits),
        )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, is_substitute
        ) VALUES (100, 99, 2026, ?, '2026-04-01', 1, 0, 0, 1)
        """,
        (GIANTS,),
    )
    aggregator.conn.commit()

    result = check_team_game_batting(aggregator.conn, 100, GIANTS)
    assert result["starter_all_hit"] is True
    assert result["starter_all_rbi"] is True
    assert result["all_hit"] is False


def test_team_no_hitter_detection(aggregator: Aggregator) -> None:
    _seed_game(aggregator)
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, er,
            is_no_hitter, is_perfect_game
        ) VALUES (100, 50, 2026, ?, '2026-04-01', 27, 0, 1, 0)
        """,
        (GIANTS,),
    )
    aggregator.conn.commit()

    result = check_team_game_pitching(aggregator.conn, 100, GIANTS)
    assert result["team_no_hitter"] is True
    assert result["team_perfect_game"] is False


def test_team_season_wins_threshold(tracked_checker: MilestoneChecker, aggregator) -> None:
    for game_id in range(1, 90):
        _seed_game(
            aggregator,
            game_id=game_id,
            home_score=4,
            away_score=1,
        )
    _seed_game(aggregator, game_id=90, home_score=4, away_score=1)
    assert get_team_wins(aggregator.conn, GIANTS, 2026) == 90

    achievements = tracked_checker.check_new_games([90], season=2026)
    keys = {item.milestone.key for item in achievements}
    assert "team_season_wins_90" in keys
    assert "team_season_wins_100" not in keys


def test_team_game_on_import(tracked_checker: MilestoneChecker, aggregator) -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    result = aggregator.import_boxscore(data, season=2026)
    assert result.error is None

    achievements = tracked_checker.check_new_games([data.meta.game_id], season=2026)
    team_keys = {
        item.milestone.key
        for item in achievements
        if item.milestone.scope.startswith("team_")
    }
    assert isinstance(team_keys, set)


def test_manual_team_milestone_duplicate(
    tracked_checker: MilestoneChecker, aggregator
) -> None:
    assert tracked_checker.record_manual_team_milestone(
        team=GIANTS,
        milestone_key="team_season_world_series_win",
        season=2026,
        achieved_date="2026-10-30",
        notes="테스트",
    )
    assert not tracked_checker.record_manual_team_milestone(
        team=GIANTS,
        milestone_key="team_season_world_series_win",
        season=2026,
        achieved_date="2026-10-31",
    )


def test_team_game_duplicate_prevention(
    tracked_checker: MilestoneChecker, aggregator
) -> None:
    _seed_game(aggregator)
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, er,
            is_no_hitter, is_perfect_game
        ) VALUES (100, 50, 2026, ?, '2026-04-01', 27, 0, 1, 0)
        """,
        (GIANTS,),
    )
    aggregator.conn.commit()

    first = tracked_checker.check_new_games([100], season=2026)
    nh = [item for item in first if item.milestone.key == "team_game_no_hitter"]
    assert nh
    tracked_checker.record_achievements(first)

    second = tracked_checker.check_new_games([100], season=2026)
    recorded_again = tracked_checker.record_achievements(second)
    row = aggregator.conn.execute(
        """
        SELECT COUNT(*) AS cnt FROM milestone_records
        WHERE team = ? AND milestone_key = 'team_game_no_hitter' AND game_id = 100
        """,
        (GIANTS,),
    ).fetchone()
    assert recorded_again == 0
    assert row["cnt"] == 1
