"""Filter roster players and bulk-edit rating fields."""

from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class RosterFilter:
    position: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_rating: float | None = None
    max_rating: float | None = None
    rating_field: str | None = None


class RosterEditor:
    """Load, filter, and bulk-modify OOTP roster CSV files."""

    def __init__(self) -> None:
        self._rows: list[dict[str, str]] = []
        self._fieldnames: list[str] = []
        self._source_path: Path | None = None

    @property
    def row_count(self) -> int:
        return len(self._rows)

    @property
    def fieldnames(self) -> list[str]:
        return list(self._fieldnames)

    def load(self, file_path: str | Path) -> None:
        path = Path(file_path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV has no header row")
            self._fieldnames = list(reader.fieldnames)
            self._rows = [dict(row) for row in reader]
        self._source_path = path

    def filter_rows(self, roster_filter: RosterFilter) -> list[dict[str, str]]:
        return [row for row in self._rows if self._matches(row, roster_filter)]

    def bulk_edit_rating(
        self,
        rows: list[dict[str, str]],
        rating_field: str,
        new_value: str | float,
    ) -> int:
        """Set rating_field on matching rows. Returns count of modified rows."""
        modified = 0
        target_ids = {id(row) for row in rows}
        for row in self._rows:
            if id(row) not in target_ids:
                continue
            if rating_field not in row and not self._has_field_case_insensitive(row, rating_field):
                continue
            key = self._resolve_field_key(row, rating_field)
            row[key] = str(new_value)
            modified += 1
        return modified

    def save(self, file_path: str | Path | None = None) -> Path:
        target = Path(file_path) if file_path else self._source_path
        if target is None:
            raise ValueError("No output path specified")

        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._fieldnames)
            writer.writeheader()
            writer.writerows(self._rows)
        return target

    def _matches(self, row: dict[str, str], roster_filter: RosterFilter) -> bool:
        checks: list[Callable[[], bool]] = []

        if roster_filter.position:
            pos = self._get_field(row, "position", "Position", "Pos")
            checks.append(lambda: pos.lower() == roster_filter.position.lower())

        if roster_filter.min_age is not None:
            age = self._parse_int(self._get_field(row, "age", "Age"))
            checks.append(lambda: age is not None and age >= roster_filter.min_age)

        if roster_filter.max_age is not None:
            age = self._parse_int(self._get_field(row, "age", "Age"))
            checks.append(lambda: age is not None and age <= roster_filter.max_age)

        if roster_filter.rating_field and (
            roster_filter.min_rating is not None or roster_filter.max_rating is not None
        ):
            rating = self._parse_float(self._get_field(row, roster_filter.rating_field))
            if roster_filter.min_rating is not None:
                checks.append(lambda: rating is not None and rating >= roster_filter.min_rating)
            if roster_filter.max_rating is not None:
                checks.append(lambda: rating is not None and rating <= roster_filter.max_rating)

        return all(check() for check in checks) if checks else True

    @staticmethod
    def _get_field(row: dict[str, str], *candidates: str) -> str:
        for key in candidates:
            if key in row:
                return row[key].strip()
            for actual_key, value in row.items():
                if actual_key.lower() == key.lower():
                    return value.strip()
        return ""

    @staticmethod
    def _parse_int(value: str) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_float(value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _has_field_case_insensitive(row: dict[str, str], field: str) -> bool:
        return any(key.lower() == field.lower() for key in row)

    @staticmethod
    def _resolve_field_key(row: dict[str, str], field: str) -> str:
        if field in row:
            return field
        for key in row:
            if key.lower() == field.lower():
                return key
        return field

    def snapshot_rows(self) -> list[dict[str, str]]:
        return deepcopy(self._rows)
