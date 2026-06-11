"""Career milestone prediction tab."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.predictor import MilestonePredictor
from core.stats.aggregator import Aggregator
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import apply_grade_style
from gui.widgets.table_widgets import SortableTable


class PredictView(QWidget):
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

        self.banner = ErrorBanner(self)
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.refresh)

        self.player_filter = QComboBox()
        self.player_filter.addItem("전체 선수", None)
        self.grade_filter = QComboBox()
        self.grade_filter.addItem("전체 등급", "")
        for grade in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_filter.addItem(grade, grade)
        self.player_filter.currentIndexChanged.connect(self.refresh)
        self.grade_filter.currentIndexChanged.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("마일스톤 예측 (통산)"))
        controls.addStretch()
        controls.addWidget(QLabel("선수:"))
        controls.addWidget(self.player_filter)
        controls.addWidget(QLabel("등급:"))
        controls.addWidget(self.grade_filter)
        controls.addWidget(self.refresh_button)

        self.table = SortableTable(
            [
                "선수",
                "마일스톤",
                "등급",
                "현재값",
                "목표값",
                "남은 수치",
                "달성률",
                "이번 시즌",
            ]
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addLayout(controls)
        layout.addWidget(self.table)

        self._reload_player_filter()
        self.refresh()

    def _reload_player_filter(self) -> None:
        current = self.player_filter.currentData()
        self.player_filter.blockSignals(True)
        self.player_filter.clear()
        self.player_filter.addItem("전체 선수", None)
        for player in self.aggregator.get_tracked_players(self.settings.tracked_teams):
            name = str(player.get("full_name") or player.get("short_name"))
            self.player_filter.addItem(name, int(player["player_id"]))
        if current is not None:
            index = self.player_filter.findData(current)
            if index >= 0:
                self.player_filter.setCurrentIndex(index)
        self.player_filter.blockSignals(False)

    def refresh(self) -> None:
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
        )
        achieved_rows = checker.get_recorded_milestones(scope="career")
        achieved = {
            (int(row["player_id"]), str(row["milestone_key"]))
            for row in achieved_rows
        }

        player_id = self.player_filter.currentData()
        player_ids = [int(player_id)] if player_id is not None else None
        predictor = MilestonePredictor(checker, self.settings.current_season)
        predictions = predictor.predict_career_all(player_ids, achieved_keys=achieved)

        grade_filter = self.grade_filter.currentData() or ""
        if grade_filter:
            predictions = [p for p in predictions if p.milestone.grade == grade_filter]

        if not predictions:
            self.banner.show_info("표시할 통산 마일스톤 예측이 없습니다.")
        else:
            self.banner.hide()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(predictions))
        for row_idx, item in enumerate(predictions):
            values = [
                item.player_name,
                item.milestone.label,
                item.milestone.grade,
                f"{item.current_value:,.0f}",
                f"{item.threshold:,.0f}",
                f"{item.remaining:,.0f}",
                f"{item.progress_pct:.1f}%",
                item.season_note,
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 2:
                    apply_grade_style(cell, item.milestone.grade)
                self.table.setItem(row_idx, col_idx, cell)
        self.table.setSortingEnabled(True)
