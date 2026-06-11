"""Milestone grade badge colors."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

GRADE_COLORS: dict[str, dict[str, str]] = {
    "common": {"bg": "#6B7280", "fg": "#FFFFFF"},
    "uncommon": {"bg": "#16A34A", "fg": "#FFFFFF"},
    "rare": {"bg": "#2563EB", "fg": "#FFFFFF"},
    "epic": {"bg": "#7C3AED", "fg": "#FFFFFF"},
    "legendary": {"bg": "#D97706", "fg": "#FFFFFF"},
}


def apply_grade_style(item: QTableWidgetItem, grade: str) -> None:
    from PyQt6.QtCore import Qt

    colors = GRADE_COLORS.get(grade, GRADE_COLORS["common"])
    item.setBackground(QColor(colors["bg"]))
    item.setForeground(QColor(colors["fg"]))
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
