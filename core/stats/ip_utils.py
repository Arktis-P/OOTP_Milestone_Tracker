"""Innings pitched conversion utilities."""

from __future__ import annotations


def ip_to_outs(ip_value: float | str) -> int:
    """Convert IP to out count. '2.1' or 2.333... → 7 outs."""
    if isinstance(ip_value, str):
        text = ip_value.strip()
        if not text:
            return 0
        parts = text.split(".")
        innings = int(parts[0])
        partial = int(parts[1]) if len(parts) > 1 else 0
        return innings * 3 + partial

    whole = int(ip_value)
    remainder = round((ip_value - whole) * 3)
    if remainder >= 3:
        whole += remainder // 3
        remainder = remainder % 3
    return whole * 3 + remainder


def outs_to_ip_str(outs: int) -> str:
    """7 outs → '2.1'."""
    if outs <= 0:
        return "0.0"
    return f"{outs // 3}.{outs % 3}"


def outs_to_ip_float(outs: int) -> float:
    """7 outs → 2.333..."""
    if outs <= 0:
        return 0.0
    return outs // 3 + (outs % 3) / 3.0
