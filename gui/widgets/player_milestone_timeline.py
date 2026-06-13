"""Career milestone timeline panel for a selected player."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from gui.widgets.grade_styles import apply_grade_to_list_item


class PlayerMilestoneTimeline(QWidget):
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
        self._records: list[dict] = []

        self.title = QLabel("커리어 마일스톤")
        self.title.setStyleSheet("font-weight: bold; padding-top: 8px;")
        self.empty_label = QLabel("아직 달성한 마일스톤이 없습니다.")
        self.empty_label.setStyleSheet("color: #9CA3AF; padding: 8px;")
        self.empty_label.setVisible(False)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(180)
        self.list_widget.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.empty_label)

    def load_player(self, player_id: int | None) -> None:
        self._records.clear()
        self.list_widget.clear()
        if player_id is None:
            self.empty_label.setText("선수를 선택하세요.")
            self.empty_label.setVisible(True)
            self.list_widget.setVisible(False)
            return

        self._records = self.aggregator.get_player_milestone_records(player_id)
        if not self._records:
            self.empty_label.setText("아직 달성한 마일스톤이 없습니다.")
            self.empty_label.setVisible(True)
            self.list_widget.setVisible(False)
            return

        self.empty_label.setVisible(False)
        self.list_widget.setVisible(True)
        for record in self._records:
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = (
                milestone.label
                if milestone
                else record.get("milestone_label", record["milestone_key"])
            )
            grade = milestone.grade if milestone else "common"
            date = record.get("achieved_date") or ""
            text = f"🏆 {date}  {label}  [{grade}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record)
            apply_grade_to_list_item(item, grade)
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return
        game_id = record.get("game_id")
        if not game_id:
            return
        logs_dir = self.settings.game_logs_dir
        if not logs_dir:
            QMessageBox.information(self, "게임 로그", "게임 로그 경로가 설정되지 않았습니다.")
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            QMessageBox.information(
                self,
                "게임 로그",
                f"파일을 찾을 수 없습니다:\n{log_path}",
            )
            return
        webbrowser.open(log_path.resolve().as_uri())
