"""Player age calculation for roster bulk edit."""

from __future__ import annotations

from datetime import date

from core.roster.ootp_format import PlayerRow
from core.roster.row_access import row_get
from core.stats.aggregator import Aggregator

DEFAULT_REFERENCE_DATE = date(2026, 3, 1)


def calculate_age(
    birth_year: int,
    birth_month: int,
    birth_day: int,
    reference_date: date,
) -> int:
    born = date(
        birth_year,
        max(1, min(birth_month, 12)),
        max(1, min(birth_day, 28)),
    )
    return (
        reference_date.year
        - born.year
        - ((reference_date.month, reference_date.day) < (born.month, born.day))
    )


def age_from_row(
    row: PlayerRow,
    fieldnames: list[str],
    reference_date: date,
) -> int | None:
    try:
        year = int(row_get(row, fieldnames, "YearOB") or 0)
        month = int(row_get(row, fieldnames, "MonthOB") or 1)
        day = int(row_get(row, fieldnames, "DayOB") or 1)
    except ValueError:
        return None
    if year <= 0:
        return None
    return calculate_age(year, month, day, reference_date)


def get_reference_date(aggregator: Aggregator, settings) -> date:
    """Prefer latest imported game date; fallback to settings or default."""
    row = aggregator.conn.execute(
        "SELECT date FROM games ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row and row["date"]:
        text = str(row["date"])[:10]
        try:
            parts = text.split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            pass
    last_import = (settings.import_state or {}).get("last_import_at", "")
    if last_import:
        text = last_import[:10]
        try:
            parts = text.split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            pass
    return DEFAULT_REFERENCE_DATE
