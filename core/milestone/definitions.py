"""Load and structure milestones.json definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Scope = Literal["career", "season"]


@dataclass(frozen=True)
class MilestoneDefinition:
    key: str
    label: str
    stat: str
    threshold: float
    scope: Scope
    category: str


class MilestoneDefinitions:
    """In-memory representation of milestones.json."""

    def __init__(self, batting: list[MilestoneDefinition], pitching: list[MilestoneDefinition]) -> None:
        self.batting = batting
        self.pitching = pitching

    @property
    def all_milestones(self) -> list[MilestoneDefinition]:
        return self.batting + self.pitching

    def get_by_key(self, key: str) -> MilestoneDefinition | None:
        for milestone in self.all_milestones:
            if milestone.key == key:
                return milestone
        return None


def load_milestones(path: str | Path) -> MilestoneDefinitions:
    """Load milestone definitions from a JSON file."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Milestones file not found: {file_path}")

    with file_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    batting = [_parse_definition(item, "batting") for item in raw.get("batting", [])]
    pitching = [_parse_definition(item, "pitching") for item in raw.get("pitching", [])]
    return MilestoneDefinitions(batting=batting, pitching=pitching)


def _parse_definition(item: dict, category: str) -> MilestoneDefinition:
    return MilestoneDefinition(
        key=item["key"],
        label=item["label"],
        stat=item["stat"],
        threshold=float(item["threshold"]),
        scope=item.get("scope", "career"),
        category=category,
    )
