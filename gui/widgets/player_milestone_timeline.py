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
from core.i18n import tr
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

        self.empty_label = QLabel(tr("No milestones achieved yet."))
        self.empty_label.setStyleSheet("color: #94a3b8; padding: 6px;")
        self.empty_label.setVisible(False)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.empty_label)

    def load_player(self, player_id: int | None) -> None:
        self._records.clear()
        self.list_widget.clear()
        if player_id is None:
            self.empty_label.setText(tr("Please select a player."))
            self.empty_label.setVisible(True)
            self.list_widget.setVisible(False)
            return

        self._records = self.aggregator.get_player_milestone_records(player_id)
        if not self._records:
            self.empty_label.setText(tr("No milestones achieved yet."))
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
            QMessageBox.information(self, tr("Game Log"), tr("Game log directory is not configured."))
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            QMessageBox.information(
                self,
                tr("Game Log"),
                tr("File not found:\n{path}").format(path=log_path),
            )
            return
        webbrowser.open(log_path.resolve().as_uri())
