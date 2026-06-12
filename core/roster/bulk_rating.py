"""Bulk roster rating modification rules (Phase 8)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from core.roster.columns import (
    BATTER_CURRENT_FIELDS,
    BATTER_POTENTIAL_FIELDS,
    DEFENSE_FIELDS,
    PITCHER_CURRENT_FIELDS,
    PITCHER_POTENTIAL_FIELDS,
    Col,
)
from core.roster.ootp_format import PlayerRow
from core.roster.position_filter import parse_position_code
from core.roster.row_access import row_get, row_set

PITCHER_POSITIONS = frozenset({11, 12, 13})
INFIELD_POSITIONS = frozenset({3, 4, 5, 6})
OUTFIELD_POSITIONS = frozenset({7, 8, 9})
CATCHER_POSITION = 2

VELOCITY_HEADER = "Velocity"
VELO_POT_NAMES = frozenset({"Velo Pot", "Velo Pot."})


class FameLevel(str, Enum):
    NONE = ""
    REGIONAL = "regional"
    NATIONAL = "national"
    SUPERSTAR = "superstar"


BASE_CURRENT_MULT = {
    FameLevel.NONE: 1.0,
    FameLevel.REGIONAL: 1.05,
    FameLevel.NATIONAL: 1.1,
    FameLevel.SUPERSTAR: 1.15,
}
BASE_POT_MULT = dict(BASE_CURRENT_MULT)
PROSPECT_CURRENT_MULT = {
    FameLevel.NONE: 1.0,
    FameLevel.REGIONAL: 1.0,
    FameLevel.NATIONAL: 1.0,
    FameLevel.SUPERSTAR: 1.05,
}
PROSPECT_POT_MULT = {
    FameLevel.NONE: 1.0,
    FameLevel.REGIONAL: 1.05,
    FameLevel.NATIONAL: 1.1,
    FameLevel.SUPERSTAR: 1.15,
}


@dataclass
class PlayerBulkSettings:
    player_id: int
    age: int
    is_prospect: bool
    prospect_manual: bool = False
    base_fame: FameLevel = FameLevel.NONE
    prospect_fame: FameLevel = FameLevel.NONE


def is_pitcher_position(position_raw: str) -> bool:
    code = parse_position_code(position_raw)
    return code in PITCHER_POSITIONS if code is not None else False


def _defense_headers_for_position(code: int | None) -> frozenset[str]:
    if code is None:
        return frozenset()
    if code in INFIELD_POSITIONS:
        return frozenset(
            {"Infield Range", "Infield Error", "Infield Arm", "DP"}
        )
    if code in OUTFIELD_POSITIONS:
        return frozenset({"OF Range", "OF Error", "OF Arm"})
    if code == CATCHER_POSITION:
        return frozenset({"CatcherAbil", "Catcher Arm", "Catcher Framing"})
    return frozenset()


def _parse_float(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_number(value: float) -> str:
    return str(int(round(value)))


def _velocity_bonus(mult: float) -> int:
    return 1 if mult >= 1.1 else 0


def _velo_pot_columns(fieldnames: list[str]) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    counts: dict[str, int] = {}
    for name in fieldnames:
        if name in VELO_POT_NAMES:
            occ = counts.get(name, 0)
            result.append((name, occ))
            counts[name] = occ + 1
    return result


def should_modify_player(settings: PlayerBulkSettings, *, prospect_boost: bool) -> bool:
    if settings.base_fame != FameLevel.NONE or settings.prospect_fame != FameLevel.NONE:
        return True
    return prospect_boost and settings.is_prospect


def _set_scaled(
    row: PlayerRow,
    fieldnames: list[str],
    col: Col,
    value: float,
) -> None:
    row_set(
        row,
        fieldnames,
        col.header,
        _format_number(value),
        occurrence=col.occurrence,
    )


def apply_bulk_rules_to_row(
    original: PlayerRow,
    fieldnames: list[str],
    settings: PlayerBulkSettings,
    *,
    prospect_boost: bool,
) -> PlayerRow:
    if not should_modify_player(settings, prospect_boost=prospect_boost):
        return original

    row = deepcopy(original)
    position = row_get(row, fieldnames, "Position")
    pos_code = parse_position_code(position)
    pitcher = is_pitcher_position(position)
    defense_headers = _defense_headers_for_position(pos_code)

    current_mult = (
        BASE_CURRENT_MULT[settings.base_fame]
        * PROSPECT_CURRENT_MULT[settings.prospect_fame]
    )
    pot_mult = (
        BASE_POT_MULT[settings.base_fame] * PROSPECT_POT_MULT[settings.prospect_fame]
    )
    velo_bonus = (
        _velocity_bonus(BASE_CURRENT_MULT[settings.base_fame])
        + _velocity_bonus(PROSPECT_CURRENT_MULT[settings.prospect_fame])
    )
    velo_pot_bonus = (
        _velocity_bonus(BASE_POT_MULT[settings.base_fame])
        + _velocity_bonus(PROSPECT_POT_MULT[settings.prospect_fame])
    )

    if not pitcher:
        for col in BATTER_CURRENT_FIELDS:
            raw = _parse_float(row_get(row, fieldnames, col.header, col.occurrence))
            if raw is None:
                continue
            _set_scaled(row, fieldnames, col, raw * current_mult)

        for col in BATTER_POTENTIAL_FIELDS:
            raw = _parse_float(row_get(row, fieldnames, col.header, col.occurrence))
            if raw is None:
                continue
            _set_scaled(row, fieldnames, col, raw * pot_mult)

        if prospect_boost and settings.is_prospect:
            for col in DEFENSE_FIELDS:
                if col.header not in defense_headers:
                    continue
                raw = _parse_float(row_get(row, fieldnames, col.header, col.occurrence))
                if raw is None:
                    continue
                _set_scaled(row, fieldnames, col, raw * 1.1)
    else:
        for col in PITCHER_CURRENT_FIELDS:
            raw = _parse_float(row_get(row, fieldnames, col.header, col.occurrence))
            if raw is None:
                continue
            if col.header == VELOCITY_HEADER:
                _set_scaled(row, fieldnames, col, raw * current_mult + velo_bonus)
            else:
                _set_scaled(row, fieldnames, col, raw * current_mult)

        velo_pot_keys = {
            (header, occ) for header, occ in _velo_pot_columns(fieldnames)
        }
        for col in PITCHER_POTENTIAL_FIELDS:
            raw = _parse_float(row_get(row, fieldnames, col.header, col.occurrence))
            if raw is None:
                continue
            key = (col.header, col.occurrence)
            if key in velo_pot_keys:
                if prospect_boost and settings.is_prospect:
                    raw += 1
                raw = raw * pot_mult + velo_pot_bonus
            else:
                raw *= pot_mult
            _set_scaled(row, fieldnames, col, raw)

        for header, occurrence in _velo_pot_columns(fieldnames):
            if any(
                col.header == header and col.occurrence == occurrence
                for col in PITCHER_POTENTIAL_FIELDS
            ):
                continue
            raw = _parse_float(row_get(row, fieldnames, header, occurrence))
            if raw is None:
                continue
            if prospect_boost and settings.is_prospect:
                raw += 1
            raw = raw * pot_mult + velo_pot_bonus
            row_set(
                row,
                fieldnames,
                header,
                _format_number(raw),
                occurrence=occurrence,
            )

    return row


def apply_bulk_to_players(
    players: Iterable,
    settings_by_id: dict[int, PlayerBulkSettings],
    fieldnames: list[str],
    *,
    prospect_boost: bool,
) -> int:
    modified = 0
    for player in players:
        settings = settings_by_id.get(player.player_id)
        if settings is None:
            continue
        if not should_modify_player(settings, prospect_boost=prospect_boost):
            continue
        player.row = apply_bulk_rules_to_row(
            player.row,
            fieldnames,
            settings,
            prospect_boost=prospect_boost,
        )
        modified += 1
    return modified
