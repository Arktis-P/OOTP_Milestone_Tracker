"""Position grouping for player list filters."""

from __future__ import annotations

from typing import Any

POSITION_GROUPS: dict[str, list[str]] = {
    "포수": ["C"],
    "내야수": ["1B", "2B", "3B", "SS"],
    "외야수": ["LF", "CF", "RF"],
    "지명타자": ["DH"],
    "투수": ["SP", "RP", "P"],
}

POSITION_FILTER_OPTIONS: list[tuple[str, str]] = [
    ("전체", ""),
    ("포수", "포수"),
    ("내야수", "내야수"),
    ("외야수", "외야수"),
    ("지명타자", "지명타자"),
    ("투수", "투수"),
]


def group_position(pos: str) -> str:
    """Classify a raw position code (e.g. 'RF, CF') into a filter group."""
    first = str(pos or "").split(",")[0].strip()
    if not first:
        return "기타"
    for group, codes in POSITION_GROUPS.items():
        if first in codes:
            return group
    return "기타"


def player_matches_position_group(player: dict[str, Any], position_group: str) -> bool:
    """Return True if player belongs to the selected position filter group."""
    if not position_group or position_group == "전체":
        return True

    codes = POSITION_GROUPS.get(position_group, [])
    pos = str(player.get("primary_position") or "")
    first = pos.split(",")[0].strip() if pos else ""

    if position_group == "투수":
        if int(player.get("is_pitcher") or 0) and not int(player.get("is_batter") or 0):
            return True

    if first and first in codes:
        return True
    return any(code in pos for code in codes)
