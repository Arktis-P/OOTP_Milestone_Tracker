"""Filter roster players and edit individual rating fields."""

from __future__ import annotations

import shutil
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.roster.ootp_format import (
    OotpRosterFile,
    PlayerRow,
    load_ootp_roster,
    player_age,
    save_ootp_roster,
)
from core.roster.position_filter import matches_position_group
from core.roster.row_access import row_as_dict, row_get


@dataclass
class RosterFilter:
    position_group: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    season_year: int = 2026

    @property
    def position(self) -> str | None:
        return self.position_group


class RosterEditor:
    """Load, filter, and modify OOTP roster export files."""

    def __init__(self) -> None:
        self._ootp: OotpRosterFile | None = None
        self._rows: list[PlayerRow] = []
        self._fieldnames: list[str] = []
        self._source_path: Path | None = None
        self._backup_saved = False
        self._season_year = 2026

    @property
    def row_count(self) -> int:
        return len(self._rows)

    @property
    def fieldnames(self) -> list[str]:
        return list(self._fieldnames)

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def backup_saved(self) -> bool:
        return self._backup_saved

    def set_season_year(self, year: int) -> None:
        self._season_year = year

    def load(self, file_path: str | Path) -> None:
        path = Path(file_path)
        if path.suffix.lower() == ".txt" or _looks_like_ootp_roster(path):
            self._ootp = load_ootp_roster(path)
            self._fieldnames = self._ootp.fieldnames
            self._rows = self._ootp.rows
        else:
            raise ValueError("지원하지 않는 로스터 형식입니다. OOTP export (.txt) 파일이 필요합니다.")
        self._source_path = path
        self._backup_saved = False

    def filter_rows(self, roster_filter: RosterFilter) -> list[PlayerRow]:
        return [row for row in self._rows if self._matches(row, roster_filter)]

    def filter_players(
        self,
        *,
        position: str | None = None,
        age_min: int | None = None,
        age_max: int | None = None,
    ) -> list[PlayerRow]:
        return self.filter_rows(
            RosterFilter(
                position_group=position,
                min_age=age_min,
                max_age=age_max,
                season_year=self._season_year,
            )
        )

    def save_copy(self, file_path: str | Path | None = None) -> Path:
        source = Path(file_path) if file_path else self._source_path
        if source is None:
            raise ValueError("No source path for backup")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = source.with_name(f"{source.stem}_backup_{stamp}{source.suffix}")
        shutil.copy2(source, backup)
        self._backup_saved = True
        return backup

    def save(self, file_path: str | Path | None = None) -> Path:
        target = Path(file_path) if file_path else self._source_path
        if target is None:
            raise ValueError("No output path specified")
        if self._ootp is None:
            raise ValueError("No OOTP roster loaded")
        self._ootp.rows = self._rows
        return save_ootp_roster(target, self._ootp)

    def snapshot_rows(self) -> list[PlayerRow]:
        return deepcopy(self._rows)

    def row_dict(self, row: PlayerRow) -> dict[str, str]:
        return row_as_dict(row, self._fieldnames)

    def _matches(self, row: PlayerRow, roster_filter: RosterFilter) -> bool:
        checks: list[Callable[[], bool]] = []
        season_year = roster_filter.season_year or self._season_year

        if roster_filter.position_group:
            pos = row_get(row, self._fieldnames, "Position")
            checks.append(
                lambda: matches_position_group(pos, roster_filter.position_group)
            )

        if roster_filter.min_age is not None:
            age = player_age(row, season_year=season_year, fieldnames=self._fieldnames)
            checks.append(lambda: age is not None and age >= roster_filter.min_age)

        if roster_filter.max_age is not None:
            age = player_age(row, season_year=season_year, fieldnames=self._fieldnames)
            checks.append(lambda: age is not None and age <= roster_filter.max_age)

        return all(check() for check in checks) if checks else True


def _looks_like_ootp_roster(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                if line.strip().startswith("//id,"):
                    return True
    except OSError:
        return False
    return False
