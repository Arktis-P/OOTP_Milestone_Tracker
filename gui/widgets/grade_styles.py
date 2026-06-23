"""Milestone grade badge colors (dark-theme friendly)."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

GRADE_COLORS: dict[str, dict[str, str | None]] = {
    "common": {"bg": None, "fg": "#9d9d9d"},
    "uncommon": {"bg": "#1a3a24", "fg": "#4ec9b0"},
    "rare": {"bg": "#1a2d4a", "fg": "#75beff"},
    "epic": {"bg": "#2d1f4a", "fg": "#c586c0"},
    "legendary": {"bg": "#3a2a10", "fg": "#dcdcaa"},
}

# Brighter foregrounds for dashboard list rows (dark background)
DASHBOARD_GRADE_FG: dict[str, str] = {
    "common": "#e8e8e8",
    "uncommon": "#6ee7b4",
    "rare": "#9cdcfe",
    "epic": "#e0a8ff",
    "legendary": "#ffe082",
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


def dashboard_milestone_color(grade: str) -> str:
    return DASHBOARD_GRADE_FG.get(grade, DASHBOARD_GRADE_FG["common"])
