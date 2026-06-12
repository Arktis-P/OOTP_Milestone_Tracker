"""Milestone record edit and delete tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.record_edit import normalize_achieved_date, validate_record_update
from core.milestone.record_edit import MilestoneRecordUpdate
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "edit.db")
    yield agg
    agg.close()


def test_normalize_achieved_date() -> None:
    assert normalize_achieved_date("260301") == "2026-03-01"
    assert normalize_achieved_date("2026-03-01") == "2026-03-01"


def test_validate_record_update_requires_season_for_team_manual() -> None:
    update = MilestoneRecordUpdate(
        achieved_date="2026-03-01",
        achieved_value=1.0,
        season=None,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    errors = validate_record_update(update, scope="team_manual")
    assert "시즌" in errors[0]


def test_update_and_delete_milestone_record(aggregator: Aggregator) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    aggregator.import_boxscore(data, season=2026)
    checker = MilestoneChecker(aggregator, load_milestones(MILESTONES_PATH))
    achievements = checker.check_new_games([data.meta.game_id], season=2026)
    career = [a for a in achievements if a.milestone.key == "career_hr_500"]
    assert career
    checker.record_achievements(career)
    row = aggregator.conn.execute(
        "SELECT id FROM milestone_records WHERE milestone_key = 'career_hr_500'"
    ).fetchone()
    record_id = int(row["id"])

    assert aggregator.update_milestone_record(
        record_id,
        achieved_date="2026-03-01",
        achieved_value=500.0,
        season=None,
        games_at_achievement=1200,
        opponent_team="Boston",
        opponent_player="Test Pitcher",
        description="통산 500호",
        notes="수정됨",
    )
    updated = aggregator.get_milestone_record_by_id(record_id)
    assert updated is not None
    assert updated["description"] == "통산 500호"
    assert updated["notes"] == "수정됨"
    assert updated["games_at_achievement"] == 1200

    assert aggregator.delete_milestone_record(record_id)
    assert aggregator.get_milestone_record_by_id(record_id) is None
