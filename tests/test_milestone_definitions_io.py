"""Milestone definition CSV save/load tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.definitions import (
    MilestoneDefinition,
    MilestoneDefinitions,
    load_milestones,
    save_milestones_csv,
    validate_milestone_definition,
)

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


def test_validate_rejects_duplicate_key() -> None:
    item = MilestoneDefinition(
        key="bat_career_hr_500",
        label="dup",
        stat="career_hr",
        threshold=500,
        scope="career",
        category="batting",
    )
    errors = validate_milestone_definition(
        item,
        existing_keys={"bat_career_hr_500"},
    )
    assert errors


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    source = load_milestones(MILESTONES_PATH)
    target = tmp_path / "milestones.csv"
    save_milestones_csv(target, source)
    reloaded = load_milestones(target)
    assert len(reloaded.all_milestones) == len(source.all_milestones)
    assert reloaded.get_by_key("bat_career_hr_500") is not None


def test_save_new_item(tmp_path: Path) -> None:
    source = load_milestones(MILESTONES_PATH)
    items = list(source.all_milestones)
    items.append(
        MilestoneDefinition(
            key="test_custom_hr",
            label="테스트 99홈런",
            stat="season_hr",
            threshold=99,
            scope="season",
            category="batting",
            grade="rare",
            description_template="situational",
        )
    )
    definitions = MilestoneDefinitions(
        batting=[item for item in items if item.category == "batting"],
        pitching=[item for item in items if item.category == "pitching"],
        team=[item for item in items if item.category == "team"],
    )
    target = tmp_path / "milestones.csv"
    save_milestones_csv(target, definitions)
    reloaded = load_milestones(target)
    assert reloaded.get_by_key("test_custom_hr") is not None
