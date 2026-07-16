"""Read-only streak center dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.streak.center_model import (
    EndedStreak,
    StreakCenterFilters,
    load_streak_center,
)
from core.streak.read_model import ActiveStreak
from gui.theme import TEXT_SECONDARY, hint_style
from gui.widgets.app_dialog import init_dialog_layout, make_button_box
from gui.widgets.empty_state import EmptyStateWidget


def _format_value_with_unit(display_value: str, unit: str) -> str:
    unit_text = tr(unit) if unit else ""
    if not unit_text:
        return display_value
    return f"{display_value} {unit_text}"


class StreakCenterDialog(QDialog):
    """A read-only view of active and stored ended streak records."""

    def __init__(
        self,
        aggregator: Aggregator,
        season: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.season = int(season)
        self.setWindowTitle(tr("Streak Center"))
        self.resize(920, 620)
        self._loading_filters = False

        layout = init_dialog_layout(self)
        title = QLabel(tr("Streak Center"))
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            tr(
                "Season {season}. Ended and best values are available stored streak records only."
            ).format(season=self.season)
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(hint_style(TEXT_SECONDARY))
        layout.addWidget(title)
        layout.addWidget(subtitle)

        layout.addWidget(self._build_filters())

        self.tabs = QTabWidget()
        self.active_table = self._make_table(
            ["Player", "Team", "Type", "Value", "Start", "Last"]
        )
        self.ended_table = self._make_table(
            ["Date", "Player", "Team", "Type", "Value", "Reason", "Stored description"]
        )

        self.active_empty = EmptyStateWidget()
        self.ended_empty = EmptyStateWidget()
        self.active_stack = QStackedWidget()
        self.active_stack.addWidget(self.active_table)
        self.active_stack.addWidget(self.active_empty)
        self.ended_stack = QStackedWidget()
        self.ended_stack.addWidget(self.ended_table)
        self.ended_stack.addWidget(self.ended_empty)

        self.tabs.addTab(self.active_stack, tr("Active"))
        self.tabs.addTab(self.ended_stack, tr("Recent Ended"))
        layout.addWidget(self.tabs, stretch=1)

        buttons = make_button_box(close=True, cancel=False)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._load()

    def _build_filters(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.player_filter = QComboBox()
        self.team_filter = QComboBox()
        self.type_filter = QComboBox()
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText(tr("Search"))

        for combo in (self.player_filter, self.team_filter, self.type_filter):
            combo.currentIndexChanged.connect(self._load)
        self.search_filter.textChanged.connect(self._load)

        layout.addWidget(QLabel(tr("Player")))
        layout.addWidget(self.player_filter, stretch=1)
        layout.addWidget(QLabel(tr("Team")))
        layout.addWidget(self.team_filter, stretch=1)
        layout.addWidget(QLabel(tr("Type")))
        layout.addWidget(self.type_filter, stretch=1)
        layout.addWidget(self.search_filter, stretch=2)
        return row

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels([tr(header) for header in headers])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _filters(self) -> StreakCenterFilters:
        return StreakCenterFilters(
            player=str(self.player_filter.currentData() or ""),
            team=str(self.team_filter.currentData() or ""),
            streak_type=str(self.type_filter.currentData() or ""),
            search=self.search_filter.text(),
        )

    def _load(self, *_args: object) -> None:
        if self._loading_filters:
            return
        try:
            model = load_streak_center(
                self.aggregator,
                self.season,
                filters=self._filters(),
            )
        except Exception:
            self.active_empty.set_content(
                "",
                tr("Streaks could not be loaded."),
                tr("The database may be unavailable or from an older version."),
            )
            self.ended_empty.set_content(
                "",
                tr("Stored ended streaks could not be loaded."),
                tr("The database may be unavailable or from an older version."),
            )
            self.active_stack.setCurrentWidget(self.active_empty)
            self.ended_stack.setCurrentWidget(self.ended_empty)
            return

        self._refresh_filter_options(
            model.player_options,
            model.team_options,
            model.type_options,
        )
        self._populate_active(model.active)
        self._populate_ended(model.ended)

    def _refresh_filter_options(
        self,
        players: list[str],
        teams: list[str],
        types: list[tuple[str, str]],
    ) -> None:
        current = self._filters()
        self._loading_filters = True
        try:
            self._set_combo(
                self.player_filter,
                [("", tr("All players"))] + [(p, p) for p in players],
                current.player,
            )
            self._set_combo(
                self.team_filter,
                [("", tr("All teams"))] + [(t, t) for t in teams],
                current.team,
            )
            self._set_combo(
                self.type_filter,
                [("", tr("All types"))] + [(key, label) for key, label in types],
                current.streak_type,
            )
        finally:
            self._loading_filters = False

    def _set_combo(
        self,
        combo: QComboBox,
        items: list[tuple[str, str]],
        selected: str,
    ) -> None:
        combo.clear()
        selected_index = 0
        for index, (value, label) in enumerate(items):
            combo.addItem(label, value)
            if value == selected:
                selected_index = index
        combo.setCurrentIndex(selected_index)

    def _populate_active(self, rows: list[ActiveStreak]) -> None:
        self.active_table.setRowCount(0)
        if not rows:
            self.active_empty.set_content(
                "",
                tr("No active streaks match these filters."),
                tr("Import boxscores or clear filters to see active streaks."),
            )
            self.active_stack.setCurrentWidget(self.active_empty)
            return
        self.active_stack.setCurrentWidget(self.active_table)
        self.active_table.setRowCount(len(rows))
        for row_index, streak in enumerate(rows):
            values = [
                streak.player_name,
                streak.team,
                streak.label,
                _format_value_with_unit(streak.display_value, streak.unit),
                streak.start_date or tr("Unknown"),
                streak.last_date or tr("Unknown"),
            ]
            self._set_row(self.active_table, row_index, values)

    def _populate_ended(self, rows: list[EndedStreak]) -> None:
        self.ended_table.setRowCount(0)
        if not rows:
            self.ended_empty.set_content(
                "",
                tr("No stored ended streak records match these filters."),
                tr("Ended streaks appear here only after streak events have been stored."),
            )
            self.ended_stack.setCurrentWidget(self.ended_empty)
            return
        self.ended_stack.setCurrentWidget(self.ended_table)
        self.ended_table.setRowCount(len(rows))
        for row_index, streak in enumerate(rows):
            values = [
                streak.achieved_date or tr("Unknown"),
                streak.player_name,
                streak.team,
                streak.label,
                _format_value_with_unit(streak.display_value, streak.unit),
                tr(streak.event_reason),
                streak.description or tr("Stored record"),
            ]
            self._set_row(self.ended_table, row_index, values)

    def _set_row(
        self,
        table: QTableWidget,
        row_index: int,
        values: list[str],
    ) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_index, column, item)
