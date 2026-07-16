"""Load and save combined MLB+KBO roster exports for bulk editing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
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
    duplicate_player_id: bool = False

    def value(self, header: str, occurrence: int = 0) -> str:
        return row_get(self.row, self.fieldnames, header, occurrence)


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


@dataclass(frozen=True)
class SafeRosterSaveResult:
    mlb_output: Path | None
    kbo_output: Path | None
    backups: tuple[Path, ...] = ()


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
    id_counts: dict[int, int] = {}

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
            id_counts[pid] = id_counts.get(pid, 0) + 1
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
    for player in result.players:
        player.duplicate_player_id = id_counts.get(player.player_id, 0) > 1
    return result


def resolve_combined_paths(import_export_dir: str | Path) -> tuple[Path | None, Path | None]:
    export_dir = Path(import_export_dir)
    mlb = find_roster_file(export_dir, "mlb")
    kbo = find_roster_file(export_dir, "kbo")
    return mlb, kbo


def save_modified_rosters(combined: CombinedRoster) -> tuple[Path | None, Path | None]:
    """Write mod_mlb_rosters.txt / mod_kbo_rosters.txt next to originals."""
    result = save_modified_rosters_safely(combined)
    return result.mlb_output, result.kbo_output


def save_modified_rosters_safely(combined: CombinedRoster) -> SafeRosterSaveResult:
    """Prepare both outputs first, then replace them with backup + rollback safety."""
    targets: list[tuple[Path, OotpRosterFile, bool]] = []
    mlb_out: Path | None = None
    kbo_out: Path | None = None
    if combined.mlb and combined.mlb_path:
        mlb_out = combined.mlb_path.with_name("mod_mlb_rosters.txt")
        targets.append((mlb_out, combined.mlb, combined.mlb_crlf))
    if combined.kbo and combined.kbo_path:
        kbo_out = combined.kbo_path.with_name("mod_kbo_rosters.txt")
        targets.append((kbo_out, combined.kbo, combined.kbo_crlf))

    for output, _roster, _crlf in targets:
        source = combined.mlb_path if output == mlb_out else combined.kbo_path
        if source is not None and output.resolve() == source.resolve():
            raise ValueError(f"Refusing to overwrite source roster: {source}")

    prepared: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    existed = {path: path.exists() for path, _roster, _crlf in targets}
    replaced: list[Path] = []
    try:
        for path, roster, use_crlf in targets:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            os.close(fd)
            temp_path = Path(temp_name)
            prepared[path] = temp_path
            _save_roster_file(temp_path, roster, use_crlf)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for path, _roster, _crlf in targets:
            if not existed[path]:
                continue
            backup = path.with_name(f"{path.name}.{timestamp}.bak")
            shutil.copy2(path, backup)
            backups[path] = backup

        for path, _roster, _crlf in targets:
            os.replace(prepared[path], path)
            prepared.pop(path, None)
            replaced.append(path)
    except Exception:
        rollback_errors: list[Exception] = []
        for path in reversed(replaced):
            try:
                backup = backups.get(path)
                if backup is not None:
                    shutil.copy2(backup, path)
                elif not existed[path] and path.exists():
                    path.unlink()
            except Exception as exc:  # pragma: no cover - exceptional filesystem failure
                rollback_errors.append(exc)
        if rollback_errors:
            raise RuntimeError(
                "Roster save failed and rollback was incomplete"
            ) from rollback_errors[0]
        raise
    finally:
        for temp_path in prepared.values():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return SafeRosterSaveResult(mlb_out, kbo_out, tuple(backups.values()))


def _save_roster_file(path: Path, roster: OotpRosterFile, use_crlf: bool) -> None:
    save_ootp_roster(path, roster)
    if use_crlf:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("\n", "\r\n"), encoding="utf-8")


def sync_player_rows_to_sources(combined: CombinedRoster) -> None:
    """Copy edited rows only to their exact source identity."""
    if not combined.mlb and not combined.kbo:
        return
    for player in combined.players:
        roster = combined.mlb if player.source == "mlb" else combined.kbo
        if roster is None:
            continue
        if player.source_row_index < 0 or player.source_row_index >= len(roster.rows):
            raise IndexError(
                f"Source row is unavailable for player {player.player_id}"
            )
        source_row = roster.rows[player.source_row_index]
        if _player_id(source_row, roster.fieldnames) != player.player_id:
            raise ValueError(
                f"Source row identity changed for player {player.player_id}"
            )
        roster.rows[player.source_row_index] = deepcopy(player.row)
