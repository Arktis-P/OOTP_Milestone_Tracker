"""Milestone achievement history tab."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
from gui.widgets.grade_styles import apply_grade_style
from gui.widgets.table_widgets import TablePanel
from gui.widgets.team_milestone_dialog import TeamMilestoneDialog


class MilestoneView(QWidget):
    records_changed = pyqtSignal()

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

        self.subject_combo = QComboBox()
        self.subject_combo.addItem("전체", "all")
        self.subject_combo.addItem("개인만", "personal")
        self.subject_combo.addItem("팀만", "team")
        self.subject_combo.currentIndexChanged.connect(self.refresh)

        self.team_filter = QComboBox()
        self.team_filter.addItem("팀 전체", "")
        self._reload_team_filter()
        self.team_filter.currentIndexChanged.connect(self.refresh)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("전체 scope", "")
        self.scope_combo.addItem("경기", "game")
        self.scope_combo.addItem("시즌", "season")
        self.scope_combo.addItem("통산", "career")
        self.scope_combo.addItem("팀 경기", "team_game")
        self.scope_combo.addItem("팀 시즌", "team_season")
        self.scope_combo.addItem("팀 수동", "team_manual")
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setSpecialValueText("전체")
        self.season_spin.setMinimum(0)
        self.season_spin.setValue(0)
        self.season_spin.valueChanged.connect(self.refresh)

        self.table_panel = TablePanel(
            ["선수/팀", "마일스톤", "등급", "scope", "달성일", "달성 수치", "시즌", "경기"],
            placeholder="선수·팀 또는 마일스톤 검색...",
        )
        self.table_panel.filter_bar.search_input.textChanged.connect(self.refresh)

        self.refresh_button = QPushButton("새로고침")
        self.manual_button = QPushButton("팀 마일스톤 수동 입력")
        self.refresh_button.clicked.connect(self.refresh)
        self.manual_button.clicked.connect(self._open_manual_dialog)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)

        button_row = QHBoxLayout()
        button_row.addWidget(QLabel("대상:"))
        button_row.addWidget(self.subject_combo)
        button_row.addWidget(QLabel("팀:"))
        button_row.addWidget(self.team_filter)
        button_row.addWidget(QLabel("scope:"))
        button_row.addWidget(self.scope_combo)
        button_row.addWidget(QLabel("시즌:"))
        button_row.addWidget(self.season_spin)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.manual_button)
        button_row.addStretch()
        button_row.addWidget(QLabel("더블클릭: 게임 로그 열기"))

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self.table_panel)

        self.refresh()

    def _reload_team_filter(self) -> None:
        current = self.team_filter.currentData()
        self.team_filter.blockSignals(True)
        self.team_filter.clear()
        self.team_filter.addItem("팀 전체", "")
        names = expand_tracked_teams(
            self.settings.tracked_teams, self.settings.custom_mlb_teams
        )
        for name in sorted(set(names)):
            self.team_filter.addItem(name, name)
        if current:
            index = self.team_filter.findData(current)
            if index >= 0:
                self.team_filter.setCurrentIndex(index)
        self.team_filter.blockSignals(False)

    def on_data_refreshed(self, kind: str) -> None:
        if kind in ("boxscore", "milestone", "all"):
            if kind == "all":
                self._reload_team_filter()
            self.refresh()

    def refresh(self) -> None:
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        scope = self.scope_combo.currentData()
        season = self.season_spin.value() or None
        search = self.table_panel.filter_bar.search_input.text().strip()
        subject = self.subject_combo.currentData() or "all"
        team = self.team_filter.currentData() or None
        self._records = checker.get_recorded_milestones(
            scope=scope or None,
            season=season,
            search=search,
            subject=subject,
            team=team or None,
        )
        self.table_panel.table.setSortingEnabled(False)
        self.table_panel.table.setRowCount(len(self._records))
        for row_idx, record in enumerate(self._records):
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = milestone.label if milestone else record.get("milestone_label", record["milestone_key"])
            grade = milestone.grade if milestone else "common"
            display_name = record["player_name"]
            if record.get("team"):
                display_name = str(record["team"])
            values = [
                display_name,
                label,
                grade,
                record.get("scope") or "",
                record["achieved_date"],
                record["achieved_value"],
                record.get("season") or "",
                record.get("game_id") or "",
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 2:
                    apply_grade_style(item, grade)
                self.table_panel.table.setItem(row_idx, col_idx, item)
        self.table_panel.table.setSortingEnabled(True)

    def _open_manual_dialog(self) -> None:
        dialog = TeamMilestoneDialog(
            self.aggregator,
            self.milestones,
            self.settings,
            parent=self,
        )
        if dialog.exec():
            self.refresh()
            self.records_changed.emit()

    def _open_game_log(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._records):
            return
        game_id = self._records[row].get("game_id")
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
