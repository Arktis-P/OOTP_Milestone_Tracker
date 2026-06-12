"""Manual milestone entry helpers and persistence."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, load_milestones
from core.milestone.manual_entry import (
    ManualMilestoneFormData,
    check_duplicate,
    get_achieved_value_candidates,
    parse_flexible_date,
    validate_manual_entry,
)
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"
GIANTS = "San Francisco Giants"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "manual.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones():
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones) -> MilestoneChecker:
    return MilestoneChecker(aggregator, milestones, season_games_total=162)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("260301", date(2026, 3, 1)),
        ("26/03/01", date(2026, 3, 1)),
        ("26-03-01", date(2026, 3, 1)),
        ("2026-03-01", date(2026, 3, 1)),
        ("2026/03/01", date(2026, 3, 1)),
        ("20260301", date(2026, 3, 1)),
    ],
)
def test_parse_flexible_date_formats(text: str, expected: date) -> None:
    assert parse_flexible_date(text) == expected


def test_parse_flexible_date_invalid() -> None:
    assert parse_flexible_date("not-a-date") is None
    assert parse_flexible_date("2026-13-01") is None


def test_achieved_value_candidates_higher(milestones) -> None:
    milestone = milestones.get_by_key("career_hr_500")
    assert milestone is not None
    assert get_achieved_value_candidates(milestone) == ["500", "501", "502", "503"]


def test_achieved_value_candidates_lower() -> None:
    milestone = MilestoneDefinition(
        key="test_era",
        label="ERA 2.00 이하",
        stat="era",
        threshold=2.0,
        scope="season",
        category="pitching",
        direction="lower",
    )
    assert get_achieved_value_candidates(milestone) == ["2", "1", "0", "-1"]


def _seed_player(aggregator: Aggregator, player_id: int = 42) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO players (player_id, full_name, short_name)
        VALUES (?, 'Aaron Judge', 'A. Judge')
        """,
        (player_id,),
    )
    aggregator.conn.commit()


def test_record_manual_player_milestone(checker: MilestoneChecker, aggregator) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("career_hr_500")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 3, 1),
        player_id=42,
        team=None,
        milestone_key="career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=1800,
        opponent_team="Boston Red Sox",
        opponent_player="",
        description="통산 500호",
        notes="수동 메모",
    )
    assert validate_manual_entry(form, milestone) == []
    record_id = checker.record_manual_milestone(form)
    row = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["player_id"] == 42
    assert row["team"] is None
    assert row["is_manual"] == 1
    assert row["game_id"] is None
    assert row["opponent_team"] == "Boston Red Sox"
    assert row["description"] == "통산 500호"
    assert row["games_at_achievement"] == 1800


def test_record_manual_team_milestone(checker: MilestoneChecker, aggregator) -> None:
    milestone = checker.definitions.get_by_key("team_manual_worldseries")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="team",
        achieved_date=date(2026, 10, 30),
        player_id=None,
        team=GIANTS,
        milestone_key="team_manual_worldseries",
        season=2026,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="",
        notes="우승",
    )
    assert validate_manual_entry(form, milestone) == []
    record_id = checker.record_manual_milestone(form)
    row = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["player_id"] == 0
    assert row["team"] == GIANTS
    assert row["is_manual"] == 1
    assert row["season"] == 2026


def test_check_duplicate_career_warns(checker: MilestoneChecker, aggregator) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("career_hr_500")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 3, 1),
        player_id=42,
        team=None,
        milestone_key="career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=100,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    checker.record_manual_milestone(form)
    kind, msg = check_duplicate(aggregator.conn, form, milestone)
    assert kind == "warn"
    assert "통산" in msg


def test_check_duplicate_same_date_game_scope_warns(
    checker: MilestoneChecker, aggregator
) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("game_hr_2")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 4, 5),
        player_id=42,
        team=None,
        milestone_key="game_hr_2",
        season=None,
        achieved_value=2.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    checker.record_manual_milestone(form)
    kind, msg = check_duplicate(aggregator.conn, form, milestone)
    assert kind == "warn"
    assert "같은 날짜" in msg
