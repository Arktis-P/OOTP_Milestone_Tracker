"""Dialog showing newly achieved milestones."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.i18n import tr
from core.milestone.checker import MilestoneAchievement
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box, table_card


class MilestoneAchievedDialog(QDialog):
    def __init__(
        self,
        achievements: list[MilestoneAchievement],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Newly Achieved Milestones"))
        self.resize(*scale_size(520, 360))

        table = QTableWidget(len(achievements), 4)
        table.setHorizontalHeaderLabels(
            [tr("Player"), tr("Milestone"), tr("Grade"), tr("Achievement Date")]
        )
        table.horizontalHeader().setStretchLastSection(True)
        for row_idx, item in enumerate(achievements):
            table.setItem(row_idx, 0, QTableWidgetItem(item.player_name))
            table.setItem(row_idx, 1, QTableWidgetItem(item.milestone.label))
            table.setItem(row_idx, 2, QTableWidgetItem(item.milestone.grade))
            table.setItem(row_idx, 3, QTableWidgetItem(item.achieved_date or ""))
        table.resizeColumnsToContents()

        buttons = make_button_box(ok=True)
        buttons.accepted.connect(self.accept)

        layout = init_dialog_layout(self)
        layout.addWidget(table_card(tr("Achievement List"), table), stretch=1)
        add_dialog_footer(layout, buttons)
