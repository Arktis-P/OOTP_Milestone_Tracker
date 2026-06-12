"""Milestone record update validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.milestone.manual_entry import parse_flexible_date


@dataclass
class MilestoneRecordUpdate:
    achieved_date: str
    achieved_value: float
    season: int | None
    games_at_achievement: int | None
    opponent_team: str
    opponent_player: str
    description: str
    notes: str


def validate_record_update(
    update: MilestoneRecordUpdate,
    *,
    scope: str,
) -> list[str]:
    errors: list[str] = []
    if not update.achieved_date.strip():
        errors.append("날짜를 입력하세요.")
    elif parse_flexible_date(update.achieved_date) is None:
        parsed_ok = _is_iso_date(update.achieved_date)
        if not parsed_ok:
            errors.append("날짜 형식을 확인하세요.")

    if scope in ("season", "season_ratio", "team_season", "team_manual"):
        if update.season is None:
            errors.append("시즌을 입력하세요.")

    return errors


def normalize_achieved_date(text: str) -> str:
    parsed = parse_flexible_date(text)
    if parsed is not None:
        return parsed.isoformat()
    raw = text.strip()
    if _is_iso_date(raw):
        return raw
    raise ValueError("날짜 형식을 확인하세요")


def parse_optional_int(text: str) -> int | None:
    raw = text.strip()
    if not raw:
        return None
    return int(raw)


def record_update_from_form(
    *,
    achieved_date: str,
    achieved_value: float,
    season_text: str,
    games_text: str,
    opponent_team: str,
    opponent_player: str,
    description: str,
    notes: str,
) -> MilestoneRecordUpdate:
    season: int | None = None
    if season_text.strip():
        season = int(season_text.strip())
    games: int | None = None
    if games_text.strip():
        games = int(games_text.strip())
    return MilestoneRecordUpdate(
        achieved_date=achieved_date.strip(),
        achieved_value=achieved_value,
        season=season,
        games_at_achievement=games,
        opponent_team=opponent_team.strip(),
        opponent_player=opponent_player.strip(),
        description=description.strip(),
        notes=notes.strip(),
    )


def _is_iso_date(text: str) -> bool:
    return parse_flexible_date(text) is not None or bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip())
    )
