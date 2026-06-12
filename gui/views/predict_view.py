"""Career milestone prediction tab."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import PredictionStore
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_player_full_names,
    load_roster_player_names,
)
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
        self._initial_load_done = False

        self.banner = ErrorBanner(self)
        self.refresh_button = QPushButton("목록 재생성")
        self.refresh_button.setToolTip(
            "추적 대상 통산 마일스톤 목록을 처음부터 다시 만듭니다.\n"
            "평소에는 박스스코어 가져오기 시 자동으로 갱신됩니다."
        )
        self.refresh_button.clicked.connect(lambda: self.refresh(force_reseed=True))

        self.player_filter = QComboBox()
        self.player_filter.addItem("전체 선수", None)
        self.grade_filter = QComboBox()
        self.grade_filter.addItem("전체 등급", "")
        for grade in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_filter.addItem(grade, grade)
        self.player_filter.currentIndexChanged.connect(self.refresh)
        self.grade_filter.currentIndexChanged.connect(self.refresh)

        self.near_only_checkbox = QCheckBox("임박만 보기")
        self.near_only_checkbox.toggled.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("마일스톤 예측 (통산)"))
        controls.addStretch()
        controls.addWidget(QLabel("선수:"))
        controls.addWidget(self.player_filter)
        controls.addWidget(QLabel("등급:"))
        controls.addWidget(self.grade_filter)
        controls.addWidget(self.near_only_checkbox)
        controls.addWidget(self.refresh_button)

        self.table = SortableTable(
            [
                "선수",
                "한글명",
                "마일스톤",
                "등급",
                "현재값",
                "목표값",
                "남은 수치",
                "달성률",
                "상태",
                "이번 시즌",
            ]
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addLayout(controls)
        layout.addWidget(self.table)

        self._reload_player_filter()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            self.refresh()

    def on_data_refreshed(self, kind: str) -> None:
        if kind in ("boxscore", "init", "milestone", "all"):
            self._reload_player_filter()
            self.refresh()

    def _prediction_store(self) -> PredictionStore:
        return PredictionStore(
            self.aggregator,
            self.milestones,
            season=self.settings.current_season,
            season_games_total=self.settings.season_games_total,
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )

    def _reload_player_filter(self) -> None:
        current = self.player_filter.currentData()
        self.player_filter.blockSignals(True)
        self.player_filter.clear()
        self.player_filter.addItem("전체 선수", None)
        for player in self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        ):
            name = str(player.get("full_name") or player.get("short_name"))
            self.player_filter.addItem(name, int(player["player_id"]))
        if current is not None:
            index = self.player_filter.findData(current)
            if index >= 0:
                self.player_filter.setCurrentIndex(index)
        self.player_filter.blockSignals(False)

    def refresh(self, *, force_reseed: bool = False) -> None:
        store = self._prediction_store()
        if force_reseed:
            store.reseed()
        else:
            store.ensure_seeded()

        player_id = self.player_filter.currentData()
        grade_filter = self.grade_filter.currentData() or ""
        predictions = store.list_cached(
            player_id=int(player_id) if player_id is not None else None,
            grade=grade_filter,
        )
        if self.near_only_checkbox.isChecked():
            predictions = [item for item in predictions if item.is_near]

        if not predictions:
            self.banner.show_info(
                "표시할 통산 마일스톤 예측이 없습니다.\n"
                "track_from 기준을 넘은 선수가 없거나, 추적 팀·박스스코어를 확인하세요."
            )
        else:
            self.banner.hide()

        mapper = load_korean_name_mapper()
        full_names = load_player_full_names(self.aggregator)
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(predictions))
        for row_idx, item in enumerate(predictions):
            grade = item.milestone.grade if item.milestone else item.grade
            status = "🔥 임박" if item.is_near else ""
            korean_name = korean_display_for_player(
                mapper,
                full_name=full_names.get(item.player_id),
                player_id=item.player_id,
                roster_names=roster_names,
            )
            values = [
                item.player_name,
                korean_name,
                item.milestone_label,
                grade,
                f"{item.current_value:,.0f}",
                f"{item.threshold:,.0f}",
                f"{item.remaining:,.0f}",
                f"{item.progress_pct:.1f}%",
                status,
                item.season_note,
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 3:
                    apply_grade_style(cell, grade)
                if col_idx == 8 and item.is_near:
                    cell.setForeground(QColor("#EF4444"))
                self.table.setItem(row_idx, col_idx, cell)
        self.table.setSortingEnabled(True)

    def focus_player(
        self, player_id: int | None = None, *, near_only: bool = False
    ) -> None:
        if near_only:
            self.near_only_checkbox.setChecked(True)
        if player_id is not None and player_id > 0:
            index = self.player_filter.findData(player_id)
            if index >= 0:
                self.player_filter.setCurrentIndex(index)
        self.refresh()
