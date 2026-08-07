"""Career milestone prediction tab."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import (
    PredictionStore,
    render_season_basis,
    render_season_note,
)
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_player_full_names,
    load_roster_player_names,
)
from core.stats.aggregator import Aggregator
from gui.widgets.card_panel import CardPanel, section_label
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import apply_grade_style
from gui.widgets.milestone_progress_delegate import (
    IS_NEAR_ROLE,
    PROGRESS_ROLE,
    MilestoneProgressDelegate,
)
from gui.widgets.table_widgets import NumericSortItem, SortableTable

_GRADE_COL = 3
_PROGRESS_COL = 4
_SEASON_COL = 6
PREDICTION_DETAIL_ROLE = Qt.ItemDataRole.UserRole + 20


def _grade_label(grade: str) -> str:
    return {
        "common": tr("Common"),
        "uncommon": tr("Uncommon"),
        "rare": tr("Rare"),
        "epic": tr("Epic"),
        "legendary": tr("Legendary"),
    }.get(grade, tr(grade.title()) if grade else "")


class PredictView(QWidget):
    player_detail_requested = pyqtSignal(int)

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
        self.refresh_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.refresh_button.setAccessibleName(tr("Regenerate prediction list"))
        self.refresh_button.setToolTip(
            tr(
                "Rebuilds the career milestone tracking list from scratch.\n"
                "Normally updated automatically when boxscores are imported."
            )
        )
        self.refresh_button.clicked.connect(lambda: self.refresh(force_reseed=True))

        self.player_filter = QComboBox()
        self.player_filter.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.player_filter.setAccessibleName(tr("Player filter"))
        self.player_filter.addItem(tr("All Players"), None)
        self.grade_filter = QComboBox()
        self.grade_filter.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grade_filter.setAccessibleName(tr("Grade filter"))
        self.grade_filter.addItem(tr("All Grades"), "")
        for grade in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_filter.addItem(_grade_label(grade), grade)
        self.player_filter.currentIndexChanged.connect(self.refresh)
        self.grade_filter.currentIndexChanged.connect(self.refresh)

        self.near_only_checkbox = QCheckBox(tr("🔥 Near Only"))
        self.near_only_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.near_only_checkbox.setAccessibleName(tr("Show near milestones only"))
        self.near_only_checkbox.toggled.connect(self.refresh)

        title = QLabel(tr("Achievement Predictions (Career)"))
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
                tr("Progress"),
                tr("Status"),
                tr("This Season"),
            ]
        )
        self.table.setToolTip(tr("Double-click a prediction to open player details."))
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setAccessibleName(tr("Career prediction table"))
        self.table.setAccessibleDescription(
            tr(
                "Each row shows the record scope, current value, target, remaining value, progress, and status."
            )
        )
        self.table.cellDoubleClicked.connect(self._open_player_details)
        self.table.currentCellChanged.connect(self._update_basis_panel)
        self._progress_delegate = MilestoneProgressDelegate(self.table)
        self.table.setItemDelegateForColumn(_PROGRESS_COL, self._progress_delegate)
        table_card = CardPanel(tr("Career Achievement Predictions"))
        table_card.add_widget(self.table)
        self.basis_label = QLabel(tr("Select a prediction to see the calculation basis."))
        self.basis_label.setObjectName("predictionBasisPanel")
        self.basis_label.setWordWrap(True)
        detail_card = CardPanel(tr("Prediction Basis"))
        detail_card.add_widget(self.basis_label)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.addWidget(table_card)
        content_splitter.addWidget(detail_card)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(filter_card)
        layout.addWidget(content_splitter, stretch=1)

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

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(predictions))
        for row_idx, item in enumerate(predictions):
            grade = item.milestone.grade if item.milestone else item.grade
            status = tr("Near") if item.is_near else ""
            korean_name = korean_display_for_player(
                mapper,
                full_name=full_names.get(item.player_id),
                player_id=item.player_id,
                roster_names=roster_names,
            )
            progress_tooltip = tr("{current:,.0f} / {target:,.0f}  ·  {pct:.1f}%").format(
                current=item.current_value, target=item.threshold, pct=item.progress_pct
            )
            progress_label = tr(
                "{current:,.0f} / {target:,.0f} · {remaining:,.0f} remaining"
            ).format(
                current=item.current_value,
                target=item.threshold,
                remaining=item.remaining,
            )
            values = [
                item.player_name,
                korean_name,
                item.milestone_label,
                _grade_label(grade),
                progress_label,
                status,
                render_season_note(item.season_note),
            ]
            for col_idx, value in enumerate(values):
                if col_idx == _PROGRESS_COL:
                    cell: QTableWidgetItem = NumericSortItem(
                        str(value), item.progress_pct
                    )
                    cell.setData(PROGRESS_ROLE, float(item.progress_pct))
                    cell.setData(IS_NEAR_ROLE, bool(item.is_near))
                    cell.setToolTip(progress_tooltip)
                else:
                    cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cell.setData(Qt.ItemDataRole.UserRole, int(item.player_id))
                cell.setData(
                    PREDICTION_DETAIL_ROLE,
                    {
                        "player": item.player_name,
                        "milestone": item.milestone_label,
                        "grade": _grade_label(grade),
                        "current": item.current_value,
                        "target": item.threshold,
                        "remaining": item.remaining,
                        "basis": render_season_basis(item.season_note),
                    },
                )
                if col_idx == _GRADE_COL:
                    apply_grade_style(cell, grade)
                if col_idx == _SEASON_COL:
                    cell.setToolTip(render_season_basis(item.season_note))
                self.table.setItem(row_idx, col_idx, cell)
        self.table.setSortingEnabled(True)
        self._update_basis_panel(self.table.currentRow(), 0, -1, -1)

    def _open_player_details(self, row: int, _column: int) -> None:
        cell = self.table.item(row, 0)
        if cell is None:
            return
        player_id = int(cell.data(Qt.ItemDataRole.UserRole) or 0)
        if player_id > 0:
            self.player_detail_requested.emit(player_id)

    def _update_basis_panel(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if current_row < 0:
            self.basis_label.setText(tr("Select a prediction to see the calculation basis."))
            return
        cell = self.table.item(current_row, 0)
        detail = cell.data(PREDICTION_DETAIL_ROLE) if cell is not None else None
        if not isinstance(detail, dict):
            self.basis_label.setText(tr("Prediction basis is unavailable for this row."))
            return
        self.basis_label.setText(
            tr(
                "{player} · {milestone}\n"
                "Grade: {grade}\n"
                "Current {current:,.0f} / Target {target:,.0f} · Remaining {remaining:,.0f}\n"
                "Basis: {basis}"
            ).format(
                player=detail["player"],
                milestone=detail["milestone"],
                grade=detail["grade"],
                current=detail["current"],
                target=detail["target"],
                remaining=detail["remaining"],
                basis=detail["basis"],
            )
        )

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
