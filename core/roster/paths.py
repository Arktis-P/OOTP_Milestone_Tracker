"""Resolve OOTP roster export paths under import_export/."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

RosterLeague = Literal["mlb", "kbo"]

_EXPORT_STEMS: dict[RosterLeague, str] = {
    "mlb": "mlb_rosters",
    "kbo": "kbo_rosters",
}

_EXPORT_LABELS: dict[RosterLeague, str] = {
    "mlb": "MLB",
    "kbo": "KBO",
}


def roster_export_stem(league: RosterLeague) -> str:
    return _EXPORT_STEMS[league]


def roster_export_label(league: RosterLeague) -> str:
    return _EXPORT_LABELS[league]


def expected_roster_path(import_export_dir: str | Path, league: RosterLeague) -> Path:
    """Primary expected path: ``{import_export_dir}/mlb_rosters`` (or kbo)."""
    return Path(import_export_dir) / roster_export_stem(league)


def find_roster_file(
    import_export_dir: str | Path | None, league: RosterLeague
) -> Path | None:
    """Return the roster CSV/txt file if it exists under import_export."""
    if not import_export_dir:
        return None
    base = expected_roster_path(import_export_dir, league)
    candidates = [base, base.with_suffix(".csv"), base.with_suffix(".txt")]
    for path in candidates:
        if path.is_file():
            return path
    if base.is_dir():
        for pattern in ("*.csv", "*.txt"):
            matches = sorted(base.glob(pattern))
            if matches:
                return matches[0]
    return None
