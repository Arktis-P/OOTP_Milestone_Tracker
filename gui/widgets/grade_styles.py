"""Milestone grade badge colors."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

GRADE_COLORS: dict[str, dict[str, str | None]] = {
    "common": {"bg": None, "fg": None},
    "uncommon": {"bg": None, "fg": None},
    "rare": {"bg": "#BAE6FD", "fg": "#0C4A6E"},
    "epic": {"bg": "#DDD6FE", "fg": "#4C1D95"},
    "legendary": {"bg": "#B45309", "fg": "#FFFBEB"},
}

_PLAYER_NAME_SQL = """
    CASE
        WHEN mr.player_id = 0 AND mr.team IS NOT NULL AND mr.team != '' THEN mr.team
        ELSE COALESCE(p.short_name, p.full_name, '')
    END
"""


def player_name_sql(alias: str = "player_name") -> str:
    """SQL expression for milestone record display name (player or team)."""
    return f"{_PLAYER_NAME_SQL} AS {alias}"


def apply_grade_style(item: QTableWidgetItem, grade: str) -> None:
    from PyQt6.QtCore import Qt

    colors = GRADE_COLORS.get(grade, GRADE_COLORS["common"])
    bg = colors.get("bg")
    fg = colors.get("fg")
    if bg:
        item.setBackground(QColor(bg))
    if fg:
        item.setForeground(QColor(fg))
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))


def apply_grade_to_list_item(item, grade: str) -> None:
    colors = GRADE_COLORS.get(grade, GRADE_COLORS["common"])
    bg = colors.get("bg")
    fg = colors.get("fg")
    if bg:
        item.setBackground(QColor(bg))
    if fg:
        item.setForeground(QColor(fg))
