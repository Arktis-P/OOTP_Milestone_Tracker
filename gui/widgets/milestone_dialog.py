"""Dialog showing newly achieved milestones."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.milestone.checker import MilestoneAchievement
from gui.ui_compact import scale_size


class MilestoneAchievedDialog(QDialog):
    def __init__(
        self,
        achievements: list[MilestoneAchievement],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("새로 달성된 마일스톤")
        self.resize(*scale_size(520, 360))

        table = QTableWidget(len(achievements), 4)
        table.setHorizontalHeaderLabels(["선수", "마일스톤", "등급", "달성일"])
        table.horizontalHeader().setStretchLastSection(True)
        for row_idx, item in enumerate(achievements):
            table.setItem(row_idx, 0, QTableWidgetItem(item.player_name))
            table.setItem(row_idx, 1, QTableWidgetItem(item.milestone.label))
            table.setItem(row_idx, 2, QTableWidgetItem(item.milestone.grade))
            table.setItem(row_idx, 3, QTableWidgetItem(item.achieved_date or ""))
        table.resizeColumnsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(table)
        layout.addWidget(buttons)
