"""Load and save OOTP roster export text files (// comment header format)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from io import StringIO
from pathlib import Path


@dataclass
class OotpRosterFile:
    lines: list[str]
    fieldnames: list[str]
    data_line_indices: list[int] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

PlayerRow = list[str]


def player_display_name(
    row: PlayerRow | dict[str, str], fieldnames: list[str] | None = None
) -> str:
    if fieldnames is not None:
        from core.roster.row_access import row_as_dict

        data = row_as_dict(row, fieldnames)
    else:
        data = row  # type: ignore[assignment]
    last = data.get("LastName", "").strip()
    first = data.get("FirstName", "").strip()
    if last and first:
        return f"{last}, {first}"
    return last or first or data.get("NickName", "").strip()


def player_age(
    row: PlayerRow | dict[str, str],
    *,
    season_year: int,
    fieldnames: list[str] | None = None,
) -> int | None:
    if fieldnames is not None:
        from core.roster.row_access import row_as_dict

        data = row_as_dict(row, fieldnames)
    else:
        data = row  # type: ignore[assignment]
    try:
        year = int(data.get("YearOB", "") or 0)
        month = int(data.get("MonthOB", "") or 1)
        day = int(data.get("DayOB", "") or 1)
    except ValueError:
        return None
    if year <= 0:
        return None
    reference = date(season_year, 7, 1)
    born = date(year, max(1, min(month, 12)), max(1, min(day, 28)))
    return (
        reference.year
        - born.year
        - ((reference.month, reference.day) < (born.month, born.day))
    )


def load_ootp_roster(file_path: str | Path) -> OotpRosterFile:
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    fieldnames: list[str] = []
    data_indices: list[int] = []
    rows: list[list[str]] = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("//id,"):
            fieldnames = _parse_header(stripped[2:])
            continue
        if not stripped or stripped.startswith("//"):
            continue
        if not fieldnames:
            continue
        rows.append(_row_from_line(line, fieldnames))
        data_indices.append(index)

    if not fieldnames:
        raise ValueError("OOTP roster header (//id, ...) not found")

    return OotpRosterFile(
        lines=lines,
        fieldnames=fieldnames,
        data_line_indices=data_indices,
        rows=rows,
    )


def save_ootp_roster(file_path: str | Path, roster: OotpRosterFile) -> Path:
    path = Path(file_path)
    lines = list(roster.lines)
    for index, row in zip(roster.data_line_indices, roster.rows):
        lines[index] = _line_from_row(row, roster.fieldnames)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parse_header(header: str) -> list[str]:
    reader = csv.reader(StringIO(header))
    names = next(reader)
    return [name.strip() for name in names]


def _row_from_line(line: str, fieldnames: list[str]) -> list[str]:
    values = next(csv.reader(StringIO(line)))
    return [
        values[index].strip() if index < len(values) else ""
        for index in range(len(fieldnames))
    ]


def _line_from_row(row: list[str], fieldnames: list[str]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="")
    padded = list(row) + [""] * max(0, len(fieldnames) - len(row))
    writer.writerow(padded[: len(fieldnames)])
    return buffer.getvalue()
