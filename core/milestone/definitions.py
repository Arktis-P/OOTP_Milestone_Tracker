"""Load and structure milestone definition files (CSV or JSON)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Scope = Literal[
    "career",
    "season",
    "game",
    "season_ratio",
    "team_game",
    "team_season",
    "team_manual",
]
Direction = Literal["higher", "lower"]
Grade = Literal["common", "uncommon", "rare", "epic", "legendary"]
Category = Literal["batting", "pitching", "team"]

ACTIVE_SCOPES = frozenset(
    {"game", "season", "career", "team_game", "team_season", "team_manual"}
)
PREDICTABLE_SCOPES = frozenset({"career"})

VALID_GRADES: frozenset[str] = frozenset(
    {"common", "uncommon", "rare", "epic", "legendary"}
)


@dataclass(frozen=True)
class MilestoneDefinition:
    key: str
    label: str
    stat: str
    threshold: float
    scope: Scope
    category: str
    direction: Direction = "higher"
    grade: Grade = "common"
    track_from: float | None = None
    active: bool = True

    def effective_track_from(self) -> float:
        """Minimum stat value before this milestone enters the prediction watch list."""
        if self.track_from is not None:
            return self.track_from
        if self.scope == "career" and self.direction == "higher":
            return self.threshold * 0.8
        return 0.0


class MilestoneDefinitions:
    """In-memory representation of milestone definitions."""

    def __init__(
        self,
        batting: list[MilestoneDefinition],
        pitching: list[MilestoneDefinition],
        team: list[MilestoneDefinition] | None = None,
    ) -> None:
        self.batting = batting
        self.pitching = pitching
        self.team = team or []

    @property
    def all_milestones(self) -> list[MilestoneDefinition]:
        return self.batting + self.pitching + self.team

    @property
    def active_milestones(self) -> list[MilestoneDefinition]:
        return [
            milestone
            for milestone in self.all_milestones
            if milestone.active and milestone.scope in ACTIVE_SCOPES
        ]

    def get_by_key(self, key: str) -> MilestoneDefinition | None:
        for milestone in self.all_milestones:
            if milestone.key == key:
                return milestone
        return None


def load_milestones(path: str | Path) -> MilestoneDefinitions:
    """Load milestone definitions from a CSV or JSON file."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Milestones file not found: {file_path}")

    if file_path.suffix.lower() == ".csv":
        return _load_csv(file_path)
    return _load_json(file_path)


def _load_csv(file_path: Path) -> MilestoneDefinitions:
    batting: list[MilestoneDefinition] = []
    pitching: list[MilestoneDefinition] = []
    team: list[MilestoneDefinition] = []
    seen_keys: set[str] = set()

    with file_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"category", "key", "label", "scope", "stat", "threshold"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(f"milestones.csv missing columns: {sorted(missing)}")

        for line_no, row in enumerate(reader, start=2):
            key = (row.get("key") or "").strip()
            if not key or key.startswith("#"):
                continue
            if key in seen_keys:
                raise ValueError(f"duplicate milestone key '{key}' at line {line_no}")
            seen_keys.add(key)

            category = (row.get("category") or "").strip().lower()
            if category not in {"batting", "pitching", "team"}:
                raise ValueError(f"invalid category '{category}' at line {line_no}")

            scope = (row.get("scope") or "").strip()
            active_raw = (row.get("active") or "true").strip().lower()
            active = active_raw not in {"false", "0", "no"}
            if scope == "season_ratio":
                active = False

            grade = (row.get("grade") or "common").strip().lower()
            if grade not in VALID_GRADES:
                raise ValueError(f"invalid grade '{grade}' at line {line_no}")

            direction = (row.get("direction") or "higher").strip().lower()
            if direction not in {"higher", "lower"}:
                raise ValueError(f"invalid direction '{direction}' at line {line_no}")

            track_raw = (row.get("track_from") or "").strip()
            track_from = float(track_raw) if track_raw else None

            item = MilestoneDefinition(
                key=key,
                label=(row.get("label") or "").strip(),
                stat=(row.get("stat") or "").strip(),
                threshold=float(row["threshold"]),
                scope=scope,  # type: ignore[arg-type]
                category=category,
                direction=direction,  # type: ignore[arg-type]
                grade=grade,  # type: ignore[arg-type]
                track_from=track_from,
                active=active,
            )
            if category == "batting":
                batting.append(item)
            elif category == "pitching":
                pitching.append(item)
            else:
                team.append(item)

    return MilestoneDefinitions(batting=batting, pitching=pitching, team=team)


def _load_json(file_path: Path) -> MilestoneDefinitions:
    with file_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    batting = [_parse_definition(item, "batting") for item in raw.get("batting", [])]
    pitching = [_parse_definition(item, "pitching") for item in raw.get("pitching", [])]
    team = [_parse_definition(item, "team") for item in raw.get("team", [])]
    return MilestoneDefinitions(batting=batting, pitching=pitching, team=team)


def _parse_definition(item: dict, category: str) -> MilestoneDefinition:
    grade = str(item.get("grade", "common")).lower()
    if grade not in VALID_GRADES:
        grade = "common"
    track_from = item.get("track_from")
    scope = item.get("scope", "career")
    active = scope != "season_ratio" and bool(item.get("active", True))
    return MilestoneDefinition(
        key=item["key"],
        label=item["label"],
        stat=item.get("stat", ""),
        threshold=float(item["threshold"]),
        scope=scope,
        category=category,
        direction=item.get("direction", "higher"),
        grade=grade,  # type: ignore[arg-type]
        track_from=float(track_from) if track_from is not None else None,
        active=active,
    )
