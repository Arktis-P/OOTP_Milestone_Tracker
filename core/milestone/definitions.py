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
Direction = Literal["higher", "lower", "boolean"]
Grade = Literal["common", "uncommon", "rare", "epic", "legendary"]
Category = Literal["batting", "pitching", "team"]

ACTIVE_SCOPES = frozenset(
    {"game", "season", "career", "team_game", "team_season", "team_manual"}
)
PREDICTABLE_SCOPES = frozenset({"career"})

VALID_GRADES: frozenset[str] = frozenset(
    {"common", "uncommon", "rare", "epic", "legendary"}
)
VALID_CATEGORIES: frozenset[str] = frozenset({"batting", "pitching", "team"})
VALID_SCOPES: frozenset[str] = frozenset(
    {
        "career",
        "season",
        "game",
        "season_ratio",
        "team_game",
        "team_season",
        "team_manual",
    }
)
VALID_DIRECTIONS: frozenset[str] = frozenset({"higher", "lower", "boolean"})
DESCRIPTION_TEMPLATES: tuple[str, ...] = (
    "",
    "situational",
    "batting_cumulative",
    "batting_event",
    "pitching_full",
    "pitching_k_only",
    "season_batting_stat",
    "season_batting_rate",
    "season_batting_composite",
    "season_batting_title",
    "season_batting_award",
    "career_batting_stat",
    "career_batting_honor",
    "season_pitching_stat",
    "season_pitching_rate",
    "season_pitching_title",
    "season_pitching_award",
    "career_pitching_stat",
    "career_pitching_honor",
    "team_game",
    "team_season",
    "team_season_event",
)
CSV_FIELDNAMES: tuple[str, ...] = (
    "category",
    "key",
    "label",
    "scope",
    "stat",
    "threshold",
    "direction",
    "grade",
    "track_from",
    "near_n",
    "description_template",
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
    near_n: float | None = None
    description_template: str = ""
    threshold_spec: str = ""
    active: bool = True

    def effective_near_n(self) -> float:
        """Absolute remaining stat count at or below which a milestone is 'near'."""
        if self.near_n is not None:
            return self.near_n
        return float(int(self.threshold * 0.05))

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

    def with_milestones(
        self,
        items: list[MilestoneDefinition],
    ) -> MilestoneDefinitions:
        batting = [item for item in items if item.category == "batting"]
        pitching = [item for item in items if item.category == "pitching"]
        team = [item for item in items if item.category == "team"]
        return MilestoneDefinitions(batting=batting, pitching=pitching, team=team)

    def replace_all(self, items: list[MilestoneDefinition]) -> MilestoneDefinitions:
        return self.with_milestones(items)


def validate_milestone_definition(
    item: MilestoneDefinition,
    *,
    existing_keys: set[str],
    editing_key: str | None = None,
) -> list[str]:
    errors: list[str] = []
    key = item.key.strip()
    if not key:
        errors.append("key를 입력하세요.")
    elif not key.replace("_", "").isalnum():
        errors.append("key는 영문·숫자·밑줄만 사용할 수 있습니다.")
    elif key in existing_keys and key != editing_key:
        errors.append(f"이미 사용 중인 key입니다: {key}")

    if item.category not in VALID_CATEGORIES:
        errors.append(f"유효하지 않은 category: {item.category}")
    if item.scope not in VALID_SCOPES:
        errors.append(f"유효하지 않은 scope: {item.scope}")
    if item.direction not in VALID_DIRECTIONS:
        errors.append(f"유효하지 않은 direction: {item.direction}")
    if item.grade not in VALID_GRADES:
        errors.append(f"유효하지 않은 grade: {item.grade}")

    if not item.label.strip():
        errors.append("표시 이름(label)을 입력하세요.")

    if item.scope != "team_manual" and not item.stat.strip():
        errors.append("stat을 입력하세요.")

    if item.threshold_spec:
        pass
    elif item.direction == "boolean":
        if item.threshold != 1:
            errors.append("boolean 기준의 threshold는 1이어야 합니다.")
    elif item.threshold <= 0 and item.scope not in {"team_manual"}:
        errors.append("threshold는 0보다 커야 합니다.")

    template = (item.description_template or "").strip()
    if template and template not in DESCRIPTION_TEMPLATES:
        errors.append(f"알 수 없는 description_template: {template}")

    return errors


def save_milestones_csv(path: str | Path, definitions: MilestoneDefinitions) -> None:
    """Write milestone definitions to CSV."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    keys: set[str] = set()
    for item in definitions.all_milestones:
        dup_errors = validate_milestone_definition(item, existing_keys=keys)
        if dup_errors:
            raise ValueError("; ".join(dup_errors))
        keys.add(item.key)

    with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        for item in definitions.all_milestones:
            writer.writerow(_definition_to_row(item))


def _definition_to_row(item: MilestoneDefinition) -> dict[str, str]:
    threshold_text = item.threshold_spec or _format_number(item.threshold)
    return {
        "category": item.category,
        "key": item.key,
        "label": item.label,
        "scope": item.scope,
        "stat": item.stat,
        "threshold": threshold_text,
        "direction": item.direction,
        "grade": item.grade,
        "track_from": _format_optional_number(item.track_from),
        "near_n": _format_optional_number(item.near_n),
        "description_template": item.description_template or "",
    }


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return ""
    return _format_number(value)


def _parse_threshold(raw: str) -> tuple[float, str]:
    text = raw.strip()
    if not text:
        return 0.0, ""
    try:
        return float(text), ""
    except ValueError:
        return 1.0, text


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
            if direction not in VALID_DIRECTIONS:
                raise ValueError(f"invalid direction '{direction}' at line {line_no}")

            track_raw = (row.get("track_from") or "").strip()
            track_from = float(track_raw) if track_raw else None

            near_raw = (row.get("near_n") or "").strip()
            near_n = float(near_raw) if near_raw else None

            description_template = (row.get("description_template") or "").strip()
            threshold, threshold_spec = _parse_threshold(row.get("threshold") or "")

            item = MilestoneDefinition(
                key=key,
                label=(row.get("label") or "").strip(),
                stat=(row.get("stat") or "").strip(),
                threshold=threshold,
                scope=scope,  # type: ignore[arg-type]
                category=category,
                direction=direction,  # type: ignore[arg-type]
                grade=grade,  # type: ignore[arg-type]
                track_from=track_from,
                near_n=near_n,
                description_template=description_template,
                threshold_spec=threshold_spec,
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
    near_n = item.get("near_n")
    scope = item.get("scope", "career")
    active = scope != "season_ratio" and bool(item.get("active", True))
    threshold, threshold_spec = _parse_threshold(str(item.get("threshold", "")))
    return MilestoneDefinition(
        key=item["key"],
        label=item["label"],
        stat=item.get("stat", ""),
        threshold=threshold,
        scope=scope,
        category=category,
        direction=item.get("direction", "higher"),
        grade=grade,  # type: ignore[arg-type]
        track_from=float(track_from) if track_from is not None else None,
        near_n=float(near_n) if near_n is not None else None,
        description_template=str(item.get("description_template", "") or ""),
        threshold_spec=threshold_spec,
        active=active,
    )
