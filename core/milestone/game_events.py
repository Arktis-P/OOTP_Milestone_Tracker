"""Single-game batting event detection from box score log rows."""

from __future__ import annotations

from typing import Any


def batting_singles(row: dict[str, Any]) -> int:
    h = int(row.get("h") or 0)
    doubles = int(row.get("doubles") or 0)
    triples = int(row.get("triples") or 0)
    hr = int(row.get("home_runs") or row.get("hr") or 0)
    return max(0, h - doubles - triples - hr)


def is_cycling_hit(row: dict[str, Any]) -> bool:
    """1B+2B+3B+HR in the same game (from box score line totals)."""
    singles = batting_singles(row)
    doubles = int(row.get("doubles") or 0)
    triples = int(row.get("triples") or 0)
    hr = int(row.get("home_runs") or row.get("hr") or 0)
    return singles >= 1 and doubles >= 1 and triples >= 1 and hr >= 1


def is_grand_slam(row: dict[str, Any]) -> bool:
    """Grand slam flag from box score BATTING notes (``3 on`` in HR detail)."""
    return bool(int(row.get("is_grand_slam") or 0))


def game_event_value(stat: str, row: dict[str, Any]) -> float | None:
    if stat == "cycle":
        return 1.0 if is_cycling_hit(row) else 0.0
    if stat == "grand_slam":
        return 1.0 if is_grand_slam(row) else 0.0
    return None
