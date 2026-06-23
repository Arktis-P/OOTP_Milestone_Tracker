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
from core.i18n import tr
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import PredictionStore, render_season_note
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_player_full_names,
    load_roster_player_names,
)
from core.stats.aggregator import Aggregator
from gui.theme import RED_BG, RED_TEXT
from gui.widgets.card_panel import CardPanel, section_label
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
        self.refresh_button = QPushButton(tr("🔄 Regenerate List"))
        self.refresh_button.setToolTip(
            tr(
                "Rebuilds the career milestone tracking list from scratch.\n"
                "Normally updated automatically when boxscores are imported."
            )
        )
        self.refresh_button.clicked.connect(lambda: self.refresh(force_reseed=True))

        self.player_filter = QComboBox()
        self.player_filter.addItem(tr("All Players"), None)
        self.grade_filter = QComboBox()
        self.grade_filter.addItem(tr("All Grades"), "")
        for grade in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_filter.addItem(grade, grade)
        self.player_filter.currentIndexChanged.connect(self.refresh)
        self.grade_filter.currentIndexChanged.connect(self.refresh)

        self.near_only_checkbox = QCheckBox(tr("🔥 Near Only"))
        self.near_only_checkbox.toggled.connect(self.refresh)

        title = QLabel(tr("Milestone Predictions (Career)"))
        title.setObjectName("pageTitle")

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(title)
        controls.addStretch()
        controls.addWidget(section_label(tr("Player")))
        controls.addWidget(self.player_filter)
        controls.addWidget(section_label(tr("Grade")))
        controls.addWidget(self.grade_filter)
        controls.addWidget(self.near_only_checkbox)
        controls.addWidget(self.refresh_button)

        filter_card = CardPanel()
        filter_card.content_layout.addLayout(controls)

        self.table = SortableTable(
            [
                tr("Player"),
                tr("Korean Name"),
                tr("Milestone"),
                tr("Grade"),
                tr("Current"),
                tr("Target"),
                tr("Remaining"),
                tr("Progress"),
                tr("Status"),
                tr("This Season"),
            ]
        )
        table_card = CardPanel(tr("Career Milestone Predictions"))
        table_card.add_widget(self.table)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(filter_card)
        layout.addWidget(table_card, stretch=1)

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
        self.player_filter.addItem(tr("All Players"), None)
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
        if self.aggregator.is_closed:
            return
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
                tr(
                    "No career milestone predictions to display.\n"
                    "No players are within tracking range, or check your tracked teams and boxscores."
                )
            )
        else:
            self.banner.hide()

        mapper = load_korean_name_mapper()
        full_names = load_player_full_names(self.aggregator)
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir
        )

        near_row_bg = QColor(RED_BG)
        near_row_fg = QColor(RED_TEXT)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(predictions))
        for row_idx, item in enumerate(predictions):
            grade = item.milestone.grade if item.milestone else item.grade
            status = tr("🔥 Near") if item.is_near else ""
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
                render_season_note(item.season_note),
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if item.is_near:
                    cell.setBackground(near_row_bg)
                    if col_idx != 3:
                        cell.setForeground(near_row_fg)
                if col_idx == 3:
                    apply_grade_style(cell, grade)
                    if item.is_near:
                        cell.setBackground(near_row_bg)
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
