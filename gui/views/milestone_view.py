"""Milestone achievement history tab."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
        self._records: list[dict] = []

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("전체 scope", "")
        self.scope_combo.addItem("경기", "game")
        self.scope_combo.addItem("시즌", "season")
        self.scope_combo.addItem("통산", "career")
        self.scope_combo.addItem("시즌 비율", "season_ratio")
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setValue(self.settings.current_season)
        self.season_spin.setSpecialValueText("전체")
        self.season_spin.setMinimum(0)
        self.season_spin.setValue(0)
        self.season_spin.valueChanged.connect(self.refresh)

        self.table_panel = TablePanel(
            ["선수", "마일스톤", "등급", "scope", "달성일", "달성 수치", "시즌", "경기"],
            placeholder="선수 또는 마일스톤 검색...",
        )
        self.table_panel.search_input.textChanged.connect(self.refresh)

        self.refresh_button = QPushButton("새로고침")
        self.season_end_button = QPushButton("시즌 종료 체크")
        self.refresh_button.clicked.connect(self.refresh)
        self.season_end_button.clicked.connect(self.run_season_end_check)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)

        button_row = QHBoxLayout()
        button_row.addWidget(QLabel("scope:"))
        button_row.addWidget(self.scope_combo)
        button_row.addWidget(QLabel("시즌:"))
        button_row.addWidget(self.season_spin)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.season_end_button)
        button_row.addStretch()
        button_row.addWidget(QLabel("더블클릭: 게임 로그 열기"))

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self.table_panel)

        self.refresh()

    def refresh(self) -> None:
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
        )
        scope = self.scope_combo.currentData()
        season = self.season_spin.value() or None
        search = self.table_panel.search_input.text().strip()
        self._records = checker.get_recorded_milestones(
            scope=scope or None,
            season=season,
            search=search,
        )
        rows = []
        for record in self._records:
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = milestone.label if milestone else record.get("milestone_label", record["milestone_key"])
            grade = milestone.grade if milestone else "common"
            rows.append(
                [
                    record["player_name"],
                    label,
                    grade,
                    record.get("scope") or "",
                    record["achieved_date"],
                    record["achieved_value"],
                    record.get("season") or "",
                    record.get("game_id") or "",
                ]
            )
        self.table_panel.table.populate(rows)

    def run_season_end_check(self) -> None:
        season = self.settings.current_season
        if self.season_spin.value():
            season = self.season_spin.value()
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
        )
        achievements = checker.check_season_ratios(season)
        if not achievements:
            QMessageBox.information(
                self,
                "시즌 종료 체크",
                f"{season}시즌 비율 마일스톤 달성 없음 (또는 자격 미충족).",
            )
            return
        recorded = checker.record_achievements(achievements)
        QMessageBox.information(
            self,
            "시즌 종료 체크",
            f"{recorded}건의 비율 마일스톤을 기록했습니다.",
        )
        self.refresh()

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
