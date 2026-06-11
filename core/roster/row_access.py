"""Index-based access for OOTP roster rows (handles duplicate column names)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RowField:
    """A field reference: name plus occurrence when the CSV header repeats."""

    name: str
    occurrence: int = 0
    label: str | None = None

    @property
    def display_label(self) -> str:
        return self.label or self.name


def field_index(fieldnames: list[str], name: str, occurrence: int = 0) -> int | None:
    count = 0
    for index, field_name in enumerate(fieldnames):
        if field_name == name:
            if count == occurrence:
                return index
            count += 1
    return None


def row_get(row: list[str], fieldnames: list[str], name: str, occurrence: int = 0) -> str:
    index = field_index(fieldnames, name, occurrence)
    if index is None or index >= len(row):
        return ""
    return row[index]


def row_set(
    row: list[str],
    fieldnames: list[str],
    name: str,
    value: str,
    occurrence: int = 0,
) -> None:
    index = field_index(fieldnames, name, occurrence)
    if index is None:
        return
    while len(row) <= index:
        row.append("")
    row[index] = value


def row_set_field(row: list[str], fieldnames: list[str], field: RowField, value: str) -> None:
    row_set(row, fieldnames, field.name, value, field.occurrence)


def row_get_field(row: list[str], fieldnames: list[str], field: RowField) -> str:
    return row_get(row, fieldnames, field.name, field.occurrence)


def row_as_dict(row: list[str], fieldnames: list[str]) -> dict[str, str]:
    """View row as a dict (last duplicate column name wins)."""
    padded = list(row) + [""] * max(0, len(fieldnames) - len(row))
    return {name: padded[index] for index, name in enumerate(fieldnames)}
