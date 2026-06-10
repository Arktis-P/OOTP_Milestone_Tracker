"""Milestone achievement history tab."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from gui.widgets.table_widgets import TablePanel


class MilestoneView(QWidget):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings

        self.table_panel = TablePanel(
            ["선수", "마일스톤", "달성일", "달성 수치", "시즌", "메모"],
            placeholder="선수 또는 마일스톤 검색...",
        )

        self.refresh_button = QPushButton("새로고침")
        self.check_button = QPushButton("달성 여부 확인")
        self.refresh_button.clicked.connect(self.refresh)
        self.check_button.clicked.connect(self.run_check)

        button_row = QHBoxLayout()
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.check_button)
        button_row.addStretch()
        button_row.addWidget(QLabel("달성 이력을 확인하고 새 마일스톤을 기록합니다."))

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self.table_panel)

        self.refresh()

    def refresh(self) -> None:
        checker = MilestoneChecker(self.aggregator, self.milestones)
        records = checker.get_recorded_milestones()
        rows = []
        for record in records:
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = milestone.label if milestone else record["milestone_key"]
            rows.append(
                [
                    record["player_name"],
                    label,
                    record["achieved_date"],
                    record["achieved_value"],
                    record["season"],
                    record.get("notes") or "",
                ]
            )
        self.table_panel.table.populate(rows)

    def run_check(self) -> None:
        checker = MilestoneChecker(self.aggregator, self.milestones)
        results = checker.check_all(self.settings.current_season)
        newly_achieved = [item for item in results if item.achieved]
        if not newly_achieved:
            QMessageBox.information(self, "마일스톤 확인", "새로 달성한 마일스톤이 없습니다.")
            return

        recorded = checker.record_achievements(
            newly_achieved,
            achieved_date=str(self.settings.current_season),
            season=self.settings.current_season,
        )
        QMessageBox.information(
            self,
            "마일스톤 확인",
            f"{recorded}건의 마일스톤을 기록했습니다.",
        )
        self.refresh()
