"""Manual player registry and merge tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.manual_entry import ManualMilestoneFormData
from core.roster.player_registry import (
    PlayerRegistry,
    derive_short_name,
    names_refer_to_same_person,
)
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "registry.db")
    yield agg
    agg.close()


@pytest.fixture
def registry(aggregator: Aggregator) -> PlayerRegistry:
    return PlayerRegistry(aggregator)


@pytest.fixture
def checker(aggregator: Aggregator) -> MilestoneChecker:
    return MilestoneChecker(
        aggregator,
        load_milestones(MILESTONES_PATH),
        season_games_total=162,
    )


def test_derive_short_name() -> None:
    assert derive_short_name("Dong-ju Moon") == "D. Moon"
    assert derive_short_name("Aaron Judge") == "A. Judge"


def test_names_refer_to_same_person() -> None:
    assert names_refer_to_same_person(
        "Dong-ju Moon",
        "D. Moon",
        "D. Moon",
        "D. Moon",
    )
    assert not names_refer_to_same_person(
        "Aaron Judge",
        "A. Judge",
        "Mike Trout",
        "M. Trout",
    )


def test_add_manual_player(registry: PlayerRegistry, aggregator: Aggregator) -> None:
    player_id = registry.add_manual_player("Dong-ju Moon")
    assert player_id == -1
    row = aggregator.conn.execute(
        "SELECT full_name, short_name, is_manual FROM players WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    assert row["full_name"] == "Dong-ju Moon"
    assert row["short_name"] == "D. Moon"
    assert row["is_manual"] == 1


def test_manual_player_milestone(checker: MilestoneChecker, registry: PlayerRegistry) -> None:
    player_id = registry.add_manual_player("Dong-ju Moon")
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 4, 1),
        player_id=player_id,
        team=None,
        milestone_key="bat_career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=100,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    record_id = checker.record_manual_milestone(form)
    row = checker.aggregator.conn.execute(
        "SELECT player_id FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["player_id"] == player_id


def test_merge_manual_player_on_import(registry: PlayerRegistry, aggregator: Aggregator) -> None:
    manual_id = registry.add_manual_player("Dong-ju Moon")
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 4, 1),
        player_id=manual_id,
        team=None,
        milestone_key="bat_career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=100,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    MilestoneChecker(
        aggregator,
        load_milestones(MILESTONES_PATH),
        season_games_total=162,
    ).record_manual_milestone(form)

    aggregator.upsert_player(90001, "D. Moon", "Dong-ju Moon")
    aggregator.conn.commit()

    manual = aggregator.conn.execute(
        "SELECT 1 FROM players WHERE player_id = ?",
        (manual_id,),
    ).fetchone()
    assert manual is None

    row = aggregator.conn.execute(
        "SELECT player_id FROM milestone_records WHERE player_id = ?",
        (90001,),
    ).fetchone()
    assert row is not None

    real = aggregator.conn.execute(
        "SELECT full_name, short_name FROM players WHERE player_id = ?",
        (90001,),
    ).fetchone()
    assert real["full_name"] == "Dong-ju Moon"
    assert real["short_name"] == "D. Moon"


def test_ensure_player_reuses_manual(registry: PlayerRegistry) -> None:
    manual_id = registry.add_manual_player("Dong-ju Moon")
    assert registry.ensure_player("D. Moon") == manual_id
    assert registry.ensure_player("Dong-ju Moon") == manual_id
