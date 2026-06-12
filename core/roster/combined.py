"""Load and save combined MLB+KBO roster exports for bulk editing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.roster.columns import FREE_AGENT_TEAM_NAMES
from core.roster.ootp_format import OotpRosterFile, PlayerRow, save_ootp_roster
from core.roster.roster_cache import load_ootp_roster_cached
from core.roster.paths import find_roster_file
from core.roster.row_access import row_get

RosterSource = Literal["mlb", "kbo"]


@dataclass
class CombinedPlayer:
    player_id: int
    row: PlayerRow
    source: RosterSource
    source_row_index: int
    fieldnames: list[str]


@dataclass
class CombinedRoster:
    mlb: OotpRosterFile | None = None
    kbo: OotpRosterFile | None = None
    players: list[CombinedPlayer] = field(default_factory=list)
    mlb_path: Path | None = None
    kbo_path: Path | None = None
    mlb_crlf: bool = False
    kbo_crlf: bool = False

    @property
    def fieldnames(self) -> list[str]:
        if self.mlb:
            return self.mlb.fieldnames
        if self.kbo:
            return self.kbo.fieldnames
        return []


def _file_uses_crlf(path: Path) -> bool:
    data = path.read_bytes()
    return b"\r\n" in data


def _is_unassigned_team(team_name: str) -> bool:
    text = (team_name or "").strip()
    if not text:
        return True
    if text in FREE_AGENT_TEAM_NAMES:
        return True
    if text.lower() in {"free agent", "free agents"}:
        return True
    return False


def _player_id(row: PlayerRow, fieldnames: list[str]) -> int | None:
    try:
        return int(row_get(row, fieldnames, "id") or 0)
    except ValueError:
        return None


def load_combined_roster(
    mlb_path: str | Path | None,
    kbo_path: str | Path | None,
) -> CombinedRoster:
    """Merge MLB and KBO roster files by player id (prefer assigned-team rows)."""
    result = CombinedRoster()
    entries: dict[int, CombinedPlayer] = {}

    for source, path in (("mlb", mlb_path), ("kbo", kbo_path)):
        if not path:
            continue
        file_path = Path(path)
        if not file_path.is_file():
            continue
        roster = load_ootp_roster_cached(file_path)
        crlf = _file_uses_crlf(file_path)
        if source == "mlb":
            result.mlb = roster
            result.mlb_path = file_path
            result.mlb_crlf = crlf
        else:
            result.kbo = roster
            result.kbo_path = file_path
            result.kbo_crlf = crlf

        for row_index, row in enumerate(roster.rows):
            pid = _player_id(row, roster.fieldnames)
            if pid is None or pid <= 0:
                continue
            team = row_get(row, roster.fieldnames, "Team Name")
            candidate = CombinedPlayer(
                player_id=pid,
                row=row,
                source=source,  # type: ignore[arg-type]
                source_row_index=row_index,
                fieldnames=roster.fieldnames,
            )
            existing = entries.get(pid)
            if existing is None:
                entries[pid] = candidate
                continue
            existing_team = row_get(existing.row, existing.fieldnames, "Team Name")
            if _is_unassigned_team(existing_team) and not _is_unassigned_team(team):
                entries[pid] = candidate
            elif _is_unassigned_team(team):
                continue
            elif _is_unassigned_team(existing_team):
                entries[pid] = candidate

    result.players = sorted(entries.values(), key=lambda item: item.player_id)
    return result


def resolve_combined_paths(import_export_dir: str | Path) -> tuple[Path | None, Path | None]:
    export_dir = Path(import_export_dir)
    mlb = find_roster_file(export_dir, "mlb")
    kbo = find_roster_file(export_dir, "kbo")
    return mlb, kbo


def save_modified_rosters(combined: CombinedRoster) -> tuple[Path | None, Path | None]:
    """Write mod_mlb_rosters.txt / mod_kbo_rosters.txt next to originals."""
    mlb_out: Path | None = None
    kbo_out: Path | None = None

    if combined.mlb and combined.mlb_path:
        mlb_out = combined.mlb_path.with_name("mod_mlb_rosters.txt")
        _save_roster_file(mlb_out, combined.mlb, combined.mlb_crlf)
    if combined.kbo and combined.kbo_path:
        kbo_out = combined.kbo_path.with_name("mod_kbo_rosters.txt")
        _save_roster_file(kbo_out, combined.kbo, combined.kbo_crlf)
    return mlb_out, kbo_out


def _save_roster_file(path: Path, roster: OotpRosterFile, use_crlf: bool) -> None:
    save_ootp_roster(path, roster)
    if use_crlf:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("\n", "\r\n"), encoding="utf-8")


def sync_player_rows_to_sources(combined: CombinedRoster) -> None:
    """Copy edited row data back into source roster objects by player id."""
    if not combined.mlb and not combined.kbo:
        return
    by_id: dict[int, PlayerRow] = {
        player.player_id: player.row for player in combined.players
    }
    for roster, source in ((combined.mlb, "mlb"), (combined.kbo, "kbo")):
        if roster is None:
            continue
        for row_index, row in enumerate(roster.rows):
            pid = _player_id(row, roster.fieldnames)
            if pid is None or pid not in by_id:
                continue
            roster.rows[row_index] = deepcopy(by_id[pid])
