"""Manual milestone entry validation and helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from core.milestone.definitions import MilestoneDefinition

TargetKind = Literal["player", "team"]
DuplicateKind = Literal["none", "warn", "exists"]


@dataclass
class ManualMilestoneFormData:
    target: TargetKind
    achieved_date: date
    player_id: int | None
    team: str | None
    milestone_key: str
    season: int | None
    achieved_value: float
    games_at_achievement: int | None
    opponent_team: str
    opponent_player: str
    description: str
    notes: str


def parse_flexible_date(text: str) -> date | None:
    """Parse flexible date strings (YY/YYYY + separators or compact digits)."""
    raw = text.strip()
    if not raw:
        return None

    if re.fullmatch(r"\d{6}", raw):
        yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
        return _safe_date(2000 + yy, mm, dd)

    if re.fullmatch(r"\d{8}", raw):
        yyyy, mm, dd = int(raw[0:4]), int(raw[4:6]), int(raw[6:8])
        return _safe_date(yyyy, mm, dd)

    for sep in ("-", "/"):
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) != 3:
                return None
            try:
                y, m, d = (int(p) for p in parts)
            except ValueError:
                return None
            if y < 100:
                y += 2000
            return _safe_date(y, m, d)

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def get_achieved_value_candidates(milestone: MilestoneDefinition) -> list[str]:
    threshold = int(milestone.threshold)
    if milestone.direction == "lower":
        return [str(threshold - offset) for offset in range(0, 4)]
    return [str(threshold + offset) for offset in range(0, 4)]


def scope_needs_season(scope: str) -> bool:
    return scope in ("season", "season_ratio", "team_season", "team_manual")


def scope_needs_games_at_achievement(scope: str) -> bool:
    return scope in ("season", "career")


def milestones_for_target(
    milestones: list[MilestoneDefinition],
    target: TargetKind,
) -> list[MilestoneDefinition]:
    if target == "team":
        return [m for m in milestones if m.category == "team" and m.active]
    return [m for m in milestones if m.category != "team" and m.active]


def validate_manual_entry(
    form: ManualMilestoneFormData,
    milestone: MilestoneDefinition | None,
) -> list[str]:
    errors: list[str] = []
    if milestone is None:
        errors.append("마일스톤을 선택하세요.")
        return errors

    if form.target == "player" and not form.player_id:
        errors.append("선수를 선택하세요.")
    if form.target == "team" and not (form.team or "").strip():
        errors.append("팀을 선택하세요.")

    scope = milestone.scope
    if scope_needs_season(scope) and form.season is None:
        errors.append("시즌을 입력하세요.")
    if scope_needs_games_at_achievement(scope) and form.games_at_achievement is None:
        errors.append("동안 경기수를 입력하세요.")

    return errors


def check_duplicate(
    conn: Any,
    form: ManualMilestoneFormData,
    milestone: MilestoneDefinition,
) -> tuple[DuplicateKind, str]:
    scope = milestone.scope
    achieved_date = form.achieved_date.isoformat()

    if scope == "career" and form.target == "player":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE player_id = ? AND milestone_key = ? AND scope = 'career'
            """,
            (form.player_id, milestone.key),
        ).fetchone()
        if row:
            return "warn", "이미 기록된 통산 마일스톤입니다."

    if scope in ("season", "season_ratio") and form.target == "player":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE player_id = ? AND milestone_key = ? AND season = ?
            """,
            (form.player_id, milestone.key, form.season),
        ).fetchone()
        if row:
            return "warn", "이미 해당 시즌에 기록된 마일스톤입니다."

    if scope in ("team_season", "team_manual") and form.target == "team":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE team = ? AND milestone_key = ? AND season = ?
            """,
            (form.team, milestone.key, form.season),
        ).fetchone()
        if row:
            return "warn", "이미 해당 시즌에 기록된 팀 마일스톤입니다."

    if scope in ("game", "team_game"):
        if form.target == "player":
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE player_id = ? AND milestone_key = ? AND achieved_date = ?
                """,
                (form.player_id, milestone.key, achieved_date),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE team = ? AND milestone_key = ? AND achieved_date = ?
                """,
                (form.team, milestone.key, achieved_date),
            ).fetchone()
        if row:
            return "warn", "이미 같은 날짜에 동일 항목이 있습니다."

    return "none", ""
