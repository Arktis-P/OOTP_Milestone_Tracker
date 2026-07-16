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
    nation: str = ""
    prospect_manual: bool = False
    base_fame: FameLevel = FameLevel.NONE
    prospect_fame: FameLevel = FameLevel.NONE


@dataclass(frozen=True)
class RatingCellChange:
    header: str
    occurrence: int
    before: str
    after: str


@dataclass(frozen=True)
class PlayerRatingChange:
    player_id: int
    original_row: tuple[str, ...]
    updated_row: tuple[str, ...]
    fieldnames: tuple[str, ...]
    cells: tuple[RatingCellChange, ...]


@dataclass(frozen=True)
class RatingCellSkip:
    player_id: int
    header: str
    occurrence: int
    reason: str


@dataclass(frozen=True)
class BulkRatingPlan:
    scope_player_ids: tuple[int, ...]
    changes: tuple[PlayerRatingChange, ...]
    unchanged: tuple[tuple[int, str], ...]
    skipped: tuple[tuple[int, str], ...]
    skipped_cells: tuple[RatingCellSkip, ...] = ()

    @property
    def changed_player_count(self) -> int:
        return len(self.changes)

    @property
    def changed_cell_count(self) -> int:
        return sum(len(change.cells) for change in self.changes)

    @property
    def skipped_cell_count(self) -> int:
        return len(self.skipped_cells)


def prospect_boost_eligible(
    settings: PlayerBulkSettings,
    *,
    prospect_boost: bool,
    prospect_nation: str | None,
) -> bool:
    """Automatic prospect boost applies only for prospects in the selected nation."""
    if not prospect_boost or not settings.is_prospect:
        return False
    nation = (prospect_nation or "").strip()
    if not nation:
        return False
    return settings.nation.strip() == nation


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


def should_modify_player(
    settings: PlayerBulkSettings,
    *,
    prospect_boost: bool,
    prospect_nation: str | None = None,
) -> bool:
    if settings.base_fame != FameLevel.NONE or settings.prospect_fame != FameLevel.NONE:
        return True
    return prospect_boost_eligible(
        settings,
        prospect_boost=prospect_boost,
        prospect_nation=prospect_nation,
    )


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
    prospect_nation: str | None = None,
) -> PlayerRow:
    if not should_modify_player(
        settings,
        prospect_boost=prospect_boost,
        prospect_nation=prospect_nation,
    ):
        return original

    row = deepcopy(original)
    position = row_get(row, fieldnames, "Position")
    pos_code = parse_position_code(position)
    pitcher = is_pitcher_position(position)
    defense_headers = _defense_headers_for_position(pos_code)
    apply_prospect_boost = prospect_boost_eligible(
        settings,
        prospect_boost=prospect_boost,
        prospect_nation=prospect_nation,
    )

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

        if apply_prospect_boost:
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
                if apply_prospect_boost:
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
            if apply_prospect_boost:
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
    prospect_nation: str | None = None,
) -> int:
    modified = 0
    for player in players:
        settings = settings_by_id.get(player.player_id)
        if settings is None:
            continue
        if not should_modify_player(
            settings,
            prospect_boost=prospect_boost,
            prospect_nation=prospect_nation,
        ):
            continue
        player.row = apply_bulk_rules_to_row(
            player.row,
            fieldnames,
            settings,
            prospect_boost=prospect_boost,
            prospect_nation=prospect_nation,
        )
        modified += 1
    return modified


def _invalid_target_cells(
    row: PlayerRow,
    fieldnames: list[str],
    settings: PlayerBulkSettings,
    *,
    prospect_boost: bool,
    prospect_nation: str | None,
) -> list[tuple[str, int]]:
    """Report non-empty invalid numeric values that an active rule targets."""
    position = row_get(row, fieldnames, "Position")
    pitcher = is_pitcher_position(position)
    apply_prospect_boost = prospect_boost_eligible(
        settings,
        prospect_boost=prospect_boost,
        prospect_nation=prospect_nation,
    )
    current_mult = (
        BASE_CURRENT_MULT[settings.base_fame]
        * PROSPECT_CURRENT_MULT[settings.prospect_fame]
    )
    pot_mult = (
        BASE_POT_MULT[settings.base_fame]
        * PROSPECT_POT_MULT[settings.prospect_fame]
    )
    targets: set[tuple[str, int]] = set()
    if pitcher:
        if current_mult != 1.0:
            targets.update((col.header, col.occurrence) for col in PITCHER_CURRENT_FIELDS)
        if pot_mult != 1.0:
            targets.update((col.header, col.occurrence) for col in PITCHER_POTENTIAL_FIELDS)
        if apply_prospect_boost:
            targets.update(_velo_pot_columns(fieldnames))
    else:
        if current_mult != 1.0:
            targets.update((col.header, col.occurrence) for col in BATTER_CURRENT_FIELDS)
        if pot_mult != 1.0:
            targets.update((col.header, col.occurrence) for col in BATTER_POTENTIAL_FIELDS)
        if apply_prospect_boost:
            defense_headers = _defense_headers_for_position(parse_position_code(position))
            targets.update(
                (col.header, col.occurrence)
                for col in DEFENSE_FIELDS
                if col.header in defense_headers
            )

    invalid: list[tuple[str, int]] = []
    for header, occurrence in targets:
        raw = row_get(row, fieldnames, header, occurrence)
        if raw.strip() and _parse_float(raw) is None:
            invalid.append((header, occurrence))
    return sorted(invalid)


def build_bulk_rating_plan(
    players: Iterable,
    scope_player_ids: Iterable[int],
    settings_by_id: dict[int, PlayerBulkSettings],
    *,
    prospect_boost: bool,
    prospect_nation: str | None = None,
) -> BulkRatingPlan:
    """Build an immutable preview using the same rules that will be saved."""
    scope = tuple(dict.fromkeys(scope_player_ids))
    scope_set = set(scope)
    players_by_id: dict[int, object] = {}
    duplicate_ids: set[int] = set()
    for player in players:
        player_id = player.player_id
        if player_id not in scope_set:
            continue
        if player_id in players_by_id:
            duplicate_ids.add(player_id)
        else:
            players_by_id[player_id] = player

    changes: list[PlayerRatingChange] = []
    unchanged: list[tuple[int, str]] = []
    skipped: list[tuple[int, str]] = []
    skipped_cells: list[RatingCellSkip] = []
    for player_id in scope:
        if player_id in duplicate_ids:
            skipped.append((player_id, "duplicate player id"))
            continue
        player = players_by_id.get(player_id)
        if player is None:
            skipped.append((player_id, "player is not present in the roster"))
            continue
        settings = settings_by_id.get(player_id)
        if settings is None:
            skipped.append((player_id, "rating settings are unavailable"))
            continue
        if getattr(player, "duplicate_player_id", False):
            skipped.append((player_id, "duplicate player id in source rosters"))
            continue
        if not should_modify_player(
            settings,
            prospect_boost=prospect_boost,
            prospect_nation=prospect_nation,
        ):
            unchanged.append((player_id, "no rating rule selected"))
            continue

        original = player.row
        fieldnames = player.fieldnames
        skipped_cells.extend(
            RatingCellSkip(player_id, header, occurrence, "invalid numeric value")
            for header, occurrence in _invalid_target_cells(
                original,
                fieldnames,
                settings,
                prospect_boost=prospect_boost,
                prospect_nation=prospect_nation,
            )
        )
        updated = apply_bulk_rules_to_row(
            original,
            fieldnames,
            settings,
            prospect_boost=prospect_boost,
            prospect_nation=prospect_nation,
        )
        occurrences: dict[str, int] = {}
        cell_changes: list[RatingCellChange] = []
        for index, header in enumerate(fieldnames):
            occurrence = occurrences.get(header, 0)
            occurrences[header] = occurrence + 1
            before = original[index] if index < len(original) else ""
            after = updated[index] if index < len(updated) else ""
            if before != after:
                cell_changes.append(
                    RatingCellChange(header, occurrence, before, after)
                )
        if not cell_changes:
            unchanged.append(
                (player_id, "selected rule produced no cell changes")
            )
            continue
        changes.append(
            PlayerRatingChange(
                player_id,
                tuple(original),
                tuple(updated),
                tuple(fieldnames),
                tuple(cell_changes),
            )
        )

    return BulkRatingPlan(
        scope,
        tuple(changes),
        tuple(unchanged),
        tuple(skipped),
        tuple(skipped_cells),
    )


def apply_bulk_rating_plan(players: Iterable, plan: BulkRatingPlan) -> None:
    """Apply the exact rows shown by a previously confirmed preview."""
    player_list = list(players)
    players_by_id: dict[int, object] = {}
    for player in player_list:
        if player.player_id in players_by_id:
            raise ValueError(f"Duplicate player id while applying plan: {player.player_id}")
        players_by_id[player.player_id] = player
    for change in plan.changes:
        player = players_by_id.get(change.player_id)
        if player is None:
            raise ValueError(f"Preview player is no longer present: {change.player_id}")
        if tuple(player.fieldnames) != change.fieldnames:
            raise ValueError(f"Roster fields changed after preview: {change.player_id}")
        if tuple(player.row) != change.original_row:
            raise ValueError(f"Roster row changed after preview: {change.player_id}")
    for change in plan.changes:
        players_by_id[change.player_id].row = list(change.updated_row)
