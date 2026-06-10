"""Parse OOTP roster / career stats CSV files."""

from __future__ import annotations

import csv
from pathlib import Path

from core.stats.models import Player


class RosterCsvParseError(Exception):
    """Raised when roster CSV parsing fails."""


def parse_roster_csv(file_path: str | Path) -> list[Player]:
    """Parse an OOTP roster CSV file into a list of Player objects.

    Raises:
        RosterCsvParseError: If the file cannot be parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise RosterCsvParseError(f"File not found: {path}")

    players: list[Player] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise RosterCsvParseError("CSV has no header row")

            for row in reader:
                players.append(
                    Player(
                        name=_field(row, "name", "Name", "player_name"),
                        team=_field(row, "team", "Team"),
                        position=_field(row, "position", "Position", "Pos"),
                        bats=_field(row, "bats", "Bats"),
                        throws=_field(row, "throws", "Throws"),
                    )
                )
    except RosterCsvParseError:
        raise
    except Exception as exc:
        raise RosterCsvParseError(f"Failed to parse roster CSV: {exc}") from exc

    return players


def _field(row: dict[str, str], *candidates: str) -> str:
    for key in candidates:
        if key in row and row[key]:
            return row[key].strip()
        for actual_key, value in row.items():
            if actual_key.lower() == key.lower() and value:
                return value.strip()
    return ""
