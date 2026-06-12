"""Milestone record context enrichment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.record_context import enrich_achievement_for_record
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
SAMPLES_LOG = ROOT / "samples" / "game_logs_html"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "ctx.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones():
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones) -> MilestoneChecker:
    return MilestoneChecker(aggregator, milestones, season_games_total=162)


def _import_game(aggregator: Aggregator, name: str, season: int = 2026) -> int:
    data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
    result = aggregator.import_boxscore(data, season=season)
    assert result.error is None
    return data.meta.game_id


def test_enrich_career_sets_games_opponent_team_and_player(
    aggregator: Aggregator, checker: MilestoneChecker, milestones
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_id = _import_game(aggregator, "game_box_13.html")
    achievements = checker.check_new_games([game_id], season=2026)
    career = [a for a in achievements if a.milestone.key == "career_hr_500"]
    assert len(career) == 1
    item = career[0]

    enrich_achievement_for_record(
        aggregator,
        item,
        game_logs_dir=SAMPLES_LOG,
    )
    assert item.games_at_achievement is not None
    assert item.games_at_achievement > 0
    assert item.opponent_team
    assert item.opponent_team != item.team


def test_record_achievements_persists_context_fields(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_id = _import_game(aggregator, "game_box_13.html")
    achievements = checker.check_new_games([game_id], season=2026)
    career = [a for a in achievements if a.milestone.key == "career_hr_500"]
    checker.record_achievements(career, game_logs_dir=SAMPLES_LOG)
    row = aggregator.conn.execute(
        """
        SELECT opponent_team, games_at_achievement, opponent_player
        FROM milestone_records
        WHERE milestone_key = 'career_hr_500'
        """
    ).fetchone()
    assert row["opponent_team"]
    assert row["games_at_achievement"] is not None
    assert row["opponent_player"]


def test_game_scope_has_opponent_team_no_games(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    if not (SAMPLES_BOX / "game_box_20.html").is_file():
        pytest.skip("game_box_20 sample missing")
    game_id = _import_game(aggregator, "game_box_20.html")
    achievements = checker.check_new_games([game_id], season=2026)
    game_hr = [a for a in achievements if a.milestone.key == "game_hr_2"]
    if not game_hr:
        pytest.skip("no game_hr_2 in sample")
    item = game_hr[0]
    enrich_achievement_for_record(aggregator, item)
    assert item.opponent_team
    assert item.games_at_achievement is None
    assert item.opponent_player is None


def test_opponent_player_from_game_log_hr(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_id = _import_game(aggregator, "game_box_13.html")
    achievements = checker.check_new_games([game_id], season=2026)
    career = [a for a in achievements if a.milestone.key == "career_hr_500"]
    assert career
    item = career[0]
    enrich_achievement_for_record(
        aggregator, item, game_logs_dir=SAMPLES_LOG
    )
    assert item.opponent_player
