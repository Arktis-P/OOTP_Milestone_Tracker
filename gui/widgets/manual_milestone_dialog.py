"""Unified manual milestone entry dialog with category tabs.

Each tab shows a table (one row per record) so several records can be
entered and saved in a single pass. New rows are only added via the
"Add Row" button (never automatically while typing), so a stray edit can't
leave an unnoticed extra row behind. An "Add One at a Time" button opens the
classic single-record popup for users who prefer that flow; accepting it
appends a new row to the table.
"""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    TRANSFER_EVENT_LABELS,
    build_injury_description,
    build_trade_description,
    check_duplicate,
    get_achieved_value_candidates,
    milestones_for_manual_entry,
    parse_flexible_date,
    parse_player_name_list,
    scope_needs_games_at_achievement,
    season_if_in_season,
    validate_manual_entry,
    validate_manual_injury,
    validate_manual_transfer,
)
from core.stats.aggregator import Aggregator
from gui.ui_compact import UI_SCALE, scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box, table_card
from gui.widgets.card_panel import CardPanel
from gui.widgets.manual_entry_fields import (
    canonical_player_text,
    configure_mlb_team_combo,
    configure_player_combo,
    configure_player_multipick_combo,
    ensure_player_id_from_combo,
    first_tracked_team_name,
    tracked_team_names,
    apply_completer,
)
from gui.widgets.guided_milestone_form import GuidedMilestoneForm
from gui.widgets.single_record_dialogs import (
    SingleInjuryEntryDialog,
    SingleMilestoneEntryDialog,
    SingleTransferEntryDialog,
)

_TAB_MILESTONE = 0
_TAB_AWARD = 1
_TAB_TRANSFER = 2
_TAB_INJURY = 3

# Milestone/Award table columns
_M_DATE, _M_PLAYER, _M_TEAM, _M_MILESTONE, _M_VALUE, _M_SEASON, _M_GAMES, \
    _M_OPP_TEAM, _M_OPP_PLAYER, _M_DESC, _M_NOTES = range(11)

# Transfer table columns
_T_DATE, _T_JOINING, _T_LEAVING, _T_TYPE, _T_JOIN_TEAM, _T_COUNTERPART, \
    _T_SEASON, _T_DESC, _T_NOTES = range(9)

# Injury table columns
_I_DATE, _I_PLAYER, _I_LABEL, _I_DURATION, _I_TEAM, _I_SEASON, _I_DESC, _I_NOTES = range(8)


_required_icon_cache: QIcon | None = None


def _required_icon() -> QIcon:
    """A red asterisk icon used to mark required columns in table headers."""
    global _required_icon_cache
    if _required_icon_cache is None:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        painter.setPen(QColor("#d32f2f"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "*")
        painter.end()
        _required_icon_cache = QIcon(pixmap)
    return _required_icon_cache


def _set_header_required(table: QTableWidget, col: int, required: bool) -> None:
    item = table.horizontalHeaderItem(col)
    if item is None:
        return
    if required:
        item.setIcon(_required_icon())
        item.setToolTip(tr("Required"))
    else:
        item.setIcon(QIcon())
        item.setToolTip("")


def _mark_required_columns(table: QTableWidget, cols: tuple[int, ...]) -> None:
    for col in cols:
        _set_header_required(table, col, True)


def _scaled_column_widths(table: QTableWidget, widths: dict[int, int]) -> None:
    """Set column widths, scaled to match the dialog's compact-UI scale factor."""
    for col, width in widths.items():
        table.setColumnWidth(col, round(width * UI_SCALE))


def _row_of_widget(table: QTableWidget, widget: QWidget) -> int:
    for row in range(table.rowCount()):
        for col in range(table.columnCount()):
            if table.cellWidget(row, col) is widget:
                return row
    return -1


class ManualMilestoneDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        initial_tab: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.setWindowTitle(tr("Manual Entry"))
        self.resize(*scale_size(1560, 760))

        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), tr("Milestone"))
        self.tabs.addTab(QWidget(), tr("Award"))
        self.tabs.addTab(QWidget(), tr("Team Move"))
        self.tabs.addTab(QWidget(), tr("Injury"))
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_milestone_page())
        self.stack.addWidget(self._build_transfer_page())
        self.stack.addWidget(self._build_injury_page())

        self.mode_stack = QStackedWidget()
        self.single_mode_page = self._build_single_mode_page()
        self.mode_stack.addWidget(self.single_mode_page)
        self.mode_stack.addWidget(self.stack)

        buttons = make_button_box(save=True, save_text="Save All")
        self.bulk_save_button = next(
            (
                button
                for button in buttons.buttons()
                if buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole
            ),
            None,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        content_card = CardPanel(tr("Manual Entry"))
        content_card.add_widget(self.tabs)
        content_card.add_widget(self.mode_stack)
        self.bulk_status_label = QLabel("")
        self.bulk_status_label.setObjectName("mutedLabel")
        self.bulk_status_label.setWordWrap(True)
        content_card.add_widget(self.bulk_status_label)

        layout = init_dialog_layout(self)
        layout.addWidget(content_card, stretch=1)
        add_dialog_footer(layout, buttons)

        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(initial_tab)
        self.tabs.blockSignals(False)
        self._on_tab_changed(initial_tab)
        self._show_single_mode()

    def _build_single_mode_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            tr(
                "Add one record at a time. Choose a type below; the form shows only "
                "the fields needed for that record type. Message review corrections use the same guided fields."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        action_row = QHBoxLayout()
        self.single_milestone_button = QPushButton(tr("Add Milestone"))
        self.single_milestone_button.clicked.connect(lambda: self._open_single_entry_for_tab(_TAB_MILESTONE))
        self.single_award_button = QPushButton(tr("Add Award"))
        self.single_award_button.clicked.connect(lambda: self._open_single_entry_for_tab(_TAB_AWARD))
        self.single_transfer_button = QPushButton(tr("Add Team Move"))
        self.single_transfer_button.clicked.connect(lambda: self._open_single_entry_for_tab(_TAB_TRANSFER))
        self.single_injury_button = QPushButton(tr("Add Injury"))
        self.single_injury_button.clicked.connect(lambda: self._open_single_entry_for_tab(_TAB_INJURY))
        for button in (
            self.single_milestone_button,
            self.single_award_button,
            self.single_transfer_button,
            self.single_injury_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.bulk_mode_button = QPushButton(tr("Several records at once"))
        self.bulk_mode_button.setObjectName("linkButton")
        self.bulk_mode_button.clicked.connect(self._show_bulk_mode)
        layout.addWidget(self.bulk_mode_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _show_single_mode(self) -> None:
        self.mode_stack.setCurrentWidget(self.single_mode_page)
        if self.bulk_save_button is not None:
            self.bulk_save_button.setVisible(False)
        self.bulk_status_label.setText(
            tr("Default mode: add one record with a guided form. Use bulk mode only for multiple records.")
        )

    def _show_bulk_mode(self) -> None:
        self.mode_stack.setCurrentWidget(self.stack)
        if self.bulk_save_button is not None:
            self.bulk_save_button.setVisible(True)
        self._update_bulk_status()

    def _open_single_entry_for_tab(self, tab: int) -> None:
        self.tabs.setCurrentIndex(tab)
        if tab in (_TAB_MILESTONE, _TAB_AWARD):
            self._open_single_milestone_dialog()
        elif tab == _TAB_TRANSFER:
            self._open_single_transfer_dialog()
        elif tab == _TAB_INJURY:
            self._open_single_injury_dialog()

    # ── Milestone / Award page ──────────────────────────────────────────

    def _build_milestone_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.milestone_hint = QLabel(
            tr(
                "Enter records directly in the table below, or use "
                "'Add One at a Time' for the classic single-record form."
            )
        )
        self.milestone_hint.setWordWrap(True)

        toolbar = QHBoxLayout()
        self.milestone_add_row_button = QPushButton(tr("Add Row"))
        self.milestone_add_row_button.clicked.connect(lambda: self._add_milestone_row())
        self.milestone_add_one_button = QPushButton(tr("Add One at a Time"))
        self.milestone_add_one_button.clicked.connect(self._open_single_milestone_dialog)
        self.milestone_remove_button = QPushButton(tr("Remove Selected"))
        self.milestone_remove_button.clicked.connect(self._on_remove_milestone_rows)
        toolbar.addWidget(self.milestone_add_row_button)
        toolbar.addWidget(self.milestone_add_one_button)
        toolbar.addStretch()
        toolbar.addWidget(self.milestone_remove_button)

        self.milestone_table = QTableWidget(0, 11)
        self.milestone_table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Player"),
                tr("Team"),
                tr("Milestone"),
                tr("Achieved Value"),
                tr("Season"),
                tr("Games in"),
                tr("Opponent"),
                tr("Opp. Player"),
                tr("Description"),
                tr("Notes"),
            ]
        )
        self._style_history_table(self.milestone_table)
        self.milestone_table.horizontalHeader().setSectionResizeMode(
            _M_DESC, QHeaderView.ResizeMode.Stretch
        )
        _scaled_column_widths(self.milestone_table, {
            _M_DATE: 100, _M_PLAYER: 190, _M_TEAM: 130, _M_MILESTONE: 220,
            _M_VALUE: 90, _M_SEASON: 70, _M_GAMES: 90, _M_OPP_TEAM: 130,
            _M_OPP_PLAYER: 160, _M_NOTES: 160,
        })
        _mark_required_columns(
            self.milestone_table, (_M_DATE, _M_PLAYER, _M_MILESTONE, _M_VALUE)
        )

        layout.addWidget(self.milestone_hint)
        layout.addLayout(toolbar)
        layout.addWidget(table_card(tr("Milestone"), self.milestone_table), stretch=1)

        self._ensure_milestone_trailing_row()
        return page

    @staticmethod
    def _style_history_table(table: QTableWidget) -> None:
        """Match the look of the Milestone History table (table_widgets.SortableTable)."""
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

    def _current_category(self) -> Literal["milestone", "award"]:
        return "award" if self.tabs.currentIndex() == _TAB_AWARD else "milestone"

    def _milestone_pool(self) -> list[MilestoneDefinition]:
        category = self._current_category()
        player_pool = milestones_for_manual_entry(
            self.milestones.all_milestones, "player", category=category
        )
        team_pool = milestones_for_manual_entry(
            self.milestones.all_milestones, "team", category=category
        )
        seen: set[str] = set()
        combined: list[MilestoneDefinition] = []
        for milestone in player_pool + team_pool:
            if milestone.key in seen:
                continue
            seen.add(milestone.key)
            combined.append(milestone)
        return combined

    def _fill_target_team_combo(self, combo: QComboBox) -> None:
        combo.clear()
        combo.addItem("", "")
        for name in tracked_team_names(self.settings):
            combo.addItem(name, name)

    def _add_milestone_row(self) -> int:
        table = self.milestone_table
        row = table.rowCount()
        table.insertRow(row)

        date_edit = QLineEdit()
        date_edit.setPlaceholderText("2026-03-01")
        table.setCellWidget(row, _M_DATE, date_edit)

        player_combo = QComboBox()
        configure_player_combo(player_combo, self.aggregator, self.settings)
        table.setCellWidget(row, _M_PLAYER, player_combo)

        team_combo = QComboBox()
        team_combo.setEditable(False)
        self._fill_target_team_combo(team_combo)
        table.setCellWidget(row, _M_TEAM, team_combo)

        milestone_combo = QComboBox()
        milestone_combo.setEditable(True)
        milestone_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for milestone in self._milestone_pool():
            milestone_combo.addItem(milestone.label, milestone.key)
        apply_completer(milestone_combo)
        milestone_combo.currentIndexChanged.connect(self._on_milestone_row_milestone_changed)
        table.setCellWidget(row, _M_MILESTONE, milestone_combo)

        value_combo = QComboBox()
        value_combo.setEditable(True)
        value_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        table.setCellWidget(row, _M_VALUE, value_combo)

        season_edit = QLineEdit()
        table.setCellWidget(row, _M_SEASON, season_edit)

        games_edit = QLineEdit()
        table.setCellWidget(row, _M_GAMES, games_edit)

        opponent_combo = QComboBox()
        configure_mlb_team_combo(opponent_combo, self.settings)
        table.setCellWidget(row, _M_OPP_TEAM, opponent_combo)

        opp_player_combo = QComboBox()
        configure_player_combo(opp_player_combo, self.aggregator, self.settings)
        opp_player_combo.setCurrentText("")
        table.setCellWidget(row, _M_OPP_PLAYER, opp_player_combo)

        table.setCellWidget(row, _M_DESC, QLineEdit())
        table.setCellWidget(row, _M_NOTES, QLineEdit())

        self._refresh_milestone_row_values(row)
        self._update_bulk_status()
        return row

    def _on_milestone_row_milestone_changed(self) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        row = _row_of_widget(self.milestone_table, combo)
        if row >= 0:
            self._refresh_milestone_row_values(row)

    def _refresh_milestone_row_values(self, row: int) -> None:
        milestone_combo = self.milestone_table.cellWidget(row, _M_MILESTONE)
        value_combo = self.milestone_table.cellWidget(row, _M_VALUE)
        if not isinstance(milestone_combo, QComboBox) or not isinstance(value_combo, QComboBox):
            return
        key = milestone_combo.currentData()
        milestone = self.milestones.get_by_key(str(key)) if key else None
        value_combo.blockSignals(True)
        value_combo.clear()
        if milestone is not None:
            for candidate in get_achieved_value_candidates(milestone):
                value_combo.addItem(candidate)
            if value_combo.count():
                value_combo.setCurrentIndex(0)
        value_combo.blockSignals(False)

    def _row_is_blank_milestone(self, row: int) -> bool:
        date_edit = self.milestone_table.cellWidget(row, _M_DATE)
        return not (isinstance(date_edit, QLineEdit) and date_edit.text().strip())

    def _ensure_milestone_trailing_row(self) -> None:
        """Guarantee at least one row exists (rows are otherwise only added by button)."""
        if self.milestone_table.rowCount() == 0:
            self._add_milestone_row()

    def _on_remove_milestone_rows(self) -> None:
        rows = sorted({index.row() for index in self.milestone_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.milestone_table.removeRow(row)
        self._ensure_milestone_trailing_row()
        self._update_bulk_status()

    def _refresh_milestone_pool_for_all_rows(self) -> None:
        pool = self._milestone_pool()
        for row in range(self.milestone_table.rowCount()):
            combo = self.milestone_table.cellWidget(row, _M_MILESTONE)
            if not isinstance(combo, QComboBox):
                continue
            current_key = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for milestone in pool:
                combo.addItem(milestone.label, milestone.key)
            if current_key:
                index = combo.findData(current_key)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)
            self._refresh_milestone_row_values(row)

    def _open_single_milestone_dialog(self) -> None:
        common_date = ""
        if self.milestone_table.rowCount() > 1:
            first_date = self.milestone_table.cellWidget(0, _M_DATE)
            if isinstance(first_date, QLineEdit):
                common_date = first_date.text().strip()
        dialog = SingleMilestoneEntryDialog(
            self._current_category(),
            self.aggregator,
            self.milestones,
            self.settings,
            self,
            initial_date=common_date,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.form is None:
            return
        self._populate_milestone_row_from_form(dialog.form, dialog.milestone)

    def _populate_milestone_row_from_form(
        self, form: ManualMilestoneFormData, milestone: MilestoneDefinition
    ) -> None:
        row = self.milestone_table.rowCount() - 1
        if not self._row_is_blank_milestone(row):
            row = self._add_milestone_row()

        date_edit = self.milestone_table.cellWidget(row, _M_DATE)
        if isinstance(date_edit, QLineEdit):
            date_edit.blockSignals(True)
            date_edit.setText(form.achieved_date.isoformat())
            date_edit.blockSignals(False)

        player_combo = self.milestone_table.cellWidget(row, _M_PLAYER)
        team_combo = self.milestone_table.cellWidget(row, _M_TEAM)
        if form.target == "player" and isinstance(player_combo, QComboBox):
            index = player_combo.findData(form.player_id)
            if index < 0:
                # Player was just registered (e.g. via "+ Add Player" in the
                # popup) after this row's combo was populated — refresh it.
                configure_player_combo(player_combo, self.aggregator, self.settings)
                index = player_combo.findData(form.player_id)
            if index >= 0:
                player_combo.setCurrentIndex(index)
            else:
                player_combo.setCurrentText(self._player_display_name(form.player_id))
        elif form.target == "team" and isinstance(team_combo, QComboBox):
            index = team_combo.findData(form.team)
            if index >= 0:
                team_combo.setCurrentIndex(index)

        milestone_combo = self.milestone_table.cellWidget(row, _M_MILESTONE)
        if isinstance(milestone_combo, QComboBox):
            index = milestone_combo.findData(milestone.key)
            if index >= 0:
                milestone_combo.setCurrentIndex(index)

        self._refresh_milestone_row_values(row)

        value_combo = self.milestone_table.cellWidget(row, _M_VALUE)
        if isinstance(value_combo, QComboBox):
            value_combo.setCurrentText(self._format_achieved_value(form.achieved_value))

        if form.season is not None:
            season_edit = self.milestone_table.cellWidget(row, _M_SEASON)
            if isinstance(season_edit, QLineEdit):
                season_edit.setText(str(form.season))
        if form.games_at_achievement is not None:
            games_edit = self.milestone_table.cellWidget(row, _M_GAMES)
            if isinstance(games_edit, QLineEdit):
                games_edit.setText(str(form.games_at_achievement))

        opponent_combo = self.milestone_table.cellWidget(row, _M_OPP_TEAM)
        if isinstance(opponent_combo, QComboBox) and form.opponent_team:
            opponent_combo.setCurrentText(form.opponent_team)

        opp_player_combo = self.milestone_table.cellWidget(row, _M_OPP_PLAYER)
        if isinstance(opp_player_combo, QComboBox) and form.opponent_player:
            opp_player_combo.setCurrentText(form.opponent_player)

        desc_edit = self.milestone_table.cellWidget(row, _M_DESC)
        if isinstance(desc_edit, QLineEdit):
            desc_edit.setText(form.description)
        notes_edit = self.milestone_table.cellWidget(row, _M_NOTES)
        if isinstance(notes_edit, QLineEdit):
            notes_edit.setText(form.notes)

        self._ensure_milestone_trailing_row()
        self._update_bulk_status()

    def _player_display_name(self, player_id: int | None) -> str:
        if player_id is None:
            return ""
        row = self.aggregator.conn.execute(
            "SELECT full_name, short_name FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if row:
            return str(row["full_name"] or row["short_name"] or player_id)
        return str(player_id)

    @staticmethod
    def _format_achieved_value(value: float) -> str:
        if value == int(value):
            return str(int(value))
        return str(value)

    def _collect_milestone_entries(
        self,
    ) -> list[tuple[ManualMilestoneFormData, MilestoneDefinition]] | None:
        entries: list[tuple[ManualMilestoneFormData, MilestoneDefinition]] = []
        for row in range(self.milestone_table.rowCount()):
            if self._row_is_blank_milestone(row):
                continue
            result = self._build_milestone_row_form(row)
            if result is None:
                return None
            entries.append(result)
        return entries

    def _build_milestone_row_form(
        self, row: int
    ) -> tuple[ManualMilestoneFormData, MilestoneDefinition] | None:
        row_label = tr("Row {n}").format(n=row + 1)

        date_edit = self.milestone_table.cellWidget(row, _M_DATE)
        date_text = date_edit.text() if isinstance(date_edit, QLineEdit) else ""
        parsed = parse_flexible_date(date_text)
        if parsed is None:
            QMessageBox.warning(
                self, tr("Input Error"), f"{row_label}: " + tr("Check date format")
            )
            return None

        milestone_combo = self.milestone_table.cellWidget(row, _M_MILESTONE)
        key = milestone_combo.currentData() if isinstance(milestone_combo, QComboBox) else None
        milestone = self.milestones.get_by_key(str(key)) if key else None
        if milestone is None:
            QMessageBox.warning(
                self, tr("Input Required"), f"{row_label}: " + tr("Please select a milestone.")
            )
            return None

        value_combo = self.milestone_table.cellWidget(row, _M_VALUE)
        value_text = value_combo.currentText().strip() if isinstance(value_combo, QComboBox) else ""
        try:
            achieved_value = float(value_text)
        except ValueError:
            QMessageBox.warning(
                self, tr("Input Error"), f"{row_label}: " + tr("Achieved value must be a number.")
            )
            return None

        season_edit = self.milestone_table.cellWidget(row, _M_SEASON)
        season_text = season_edit.text().strip() if isinstance(season_edit, QLineEdit) else ""
        if season_text:
            try:
                season: int | None = int(season_text)
            except ValueError:
                QMessageBox.warning(
                    self, tr("Input Error"), f"{row_label}: " + tr("Season must be a number.")
                )
                return None
        else:
            # Blank season defaults to the year of the achieved date.
            season = parsed.year

        games_at: int | None = None
        if scope_needs_games_at_achievement(milestone.scope):
            games_edit = self.milestone_table.cellWidget(row, _M_GAMES)
            games_text = games_edit.text().strip() if isinstance(games_edit, QLineEdit) else ""
            if games_text:
                try:
                    games_at = int(games_text)
                except ValueError:
                    QMessageBox.warning(
                        self, tr("Input Error"), f"{row_label}: " + tr("Games must be an integer.")
                    )
                    return None
            elif self._current_category() != "award":
                QMessageBox.warning(
                    self, tr("Input Error"), f"{row_label}: " + tr("Games must be an integer.")
                )
                return None

        player_combo = self.milestone_table.cellWidget(row, _M_PLAYER)
        team_combo = self.milestone_table.cellWidget(row, _M_TEAM)
        player_text = player_combo.currentText().strip() if isinstance(player_combo, QComboBox) else ""
        team_value = team_combo.currentData() if isinstance(team_combo, QComboBox) else ""

        is_player = bool(player_text)
        player_id: int | None = None
        team: str | None = str(team_value) if team_value else None
        if is_player:
            player_id = ensure_player_id_from_combo(player_combo, self.aggregator)
            if player_id is None:
                QMessageBox.warning(
                    self,
                    tr("Input Required"),
                    f"{row_label}: " + tr("Select a player or enter a full name."),
                )
                return None
            if team is None:
                # Blank affiliation defaults to the topmost tracked team.
                team = first_tracked_team_name(self.settings) or None
        elif team is None:
            QMessageBox.warning(
                self,
                tr("Input Required"),
                f"{row_label}: " + tr("Select a player or enter a full name."),
            )
            return None

        opponent_combo = self.milestone_table.cellWidget(row, _M_OPP_TEAM)
        opp_player_combo = self.milestone_table.cellWidget(row, _M_OPP_PLAYER)
        desc_edit = self.milestone_table.cellWidget(row, _M_DESC)
        notes_edit = self.milestone_table.cellWidget(row, _M_NOTES)

        form = ManualMilestoneFormData(
            target="player" if is_player else "team",
            achieved_date=parsed,
            player_id=player_id,
            team=team,
            milestone_key=milestone.key,
            season=season,
            achieved_value=achieved_value,
            games_at_achievement=games_at,
            opponent_team=opponent_combo.currentText().strip() if isinstance(opponent_combo, QComboBox) else "",
            opponent_player=canonical_player_text(opp_player_combo) if isinstance(opp_player_combo, QComboBox) else "",
            description=desc_edit.text().strip() if isinstance(desc_edit, QLineEdit) else "",
            notes=notes_edit.text().strip() if isinstance(notes_edit, QLineEdit) else "",
        )
        errors = validate_manual_entry(form, milestone)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), f"{row_label}:\n" + "\n".join(errors))
            return None
        return form, milestone

    # ── Transfer page ────────────────────────────────────────────────────

    def _build_transfer_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            tr(
                "Records player transfer events such as contracts and trades. "
                "Separate multiple players with commas."
            )
        )
        hint.setWordWrap(True)

        toolbar = QHBoxLayout()
        self.transfer_add_row_button = QPushButton(tr("Add Row"))
        self.transfer_add_row_button.clicked.connect(lambda: self._add_transfer_row())
        self.transfer_add_one_button = QPushButton(tr("Add One at a Time"))
        self.transfer_add_one_button.clicked.connect(self._open_single_transfer_dialog)
        self.transfer_remove_button = QPushButton(tr("Remove Selected"))
        self.transfer_remove_button.clicked.connect(self._on_remove_transfer_rows)
        toolbar.addWidget(self.transfer_add_row_button)
        toolbar.addWidget(self.transfer_add_one_button)
        toolbar.addStretch()
        toolbar.addWidget(self.transfer_remove_button)

        self.transfer_table = QTableWidget(0, 9)
        self.transfer_table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Joining"),
                tr("Leaving"),
                tr("Type"),
                tr("Join Team"),
                tr("Counterpart Team"),
                tr("Season"),
                tr("Description"),
                tr("Notes"),
            ]
        )
        self._style_history_table(self.transfer_table)
        self.transfer_table.horizontalHeader().setSectionResizeMode(
            _T_DESC, QHeaderView.ResizeMode.Stretch
        )
        _scaled_column_widths(self.transfer_table, {
            _T_DATE: 100, _T_JOINING: 190, _T_LEAVING: 190, _T_TYPE: 150,
            _T_JOIN_TEAM: 150, _T_COUNTERPART: 150, _T_SEASON: 70, _T_NOTES: 160,
        })
        _mark_required_columns(self.transfer_table, (_T_DATE, _T_TYPE, _T_JOIN_TEAM))

        layout.addWidget(hint)
        layout.addLayout(toolbar)
        layout.addWidget(table_card(tr("Team Move"), self.transfer_table), stretch=1)

        self._ensure_transfer_trailing_row()
        return page

    def _add_transfer_row(self) -> int:
        table = self.transfer_table
        row = table.rowCount()
        table.insertRow(row)

        date_edit = QLineEdit()
        date_edit.setPlaceholderText("2026-03-01")
        table.setCellWidget(row, _T_DATE, date_edit)

        joining_combo = QComboBox()
        configure_player_multipick_combo(
            joining_combo, self.aggregator, self.settings, lambda: self._update_transfer_row_description(row)
        )
        joining_combo.lineEdit().textChanged.connect(lambda: self._update_transfer_row_description(row))
        table.setCellWidget(row, _T_JOINING, joining_combo)

        leaving_combo = QComboBox()
        configure_player_multipick_combo(
            leaving_combo, self.aggregator, self.settings, lambda: self._update_transfer_row_description(row)
        )
        leaving_combo.lineEdit().textChanged.connect(lambda: self._update_transfer_row_description(row))
        table.setCellWidget(row, _T_LEAVING, leaving_combo)

        type_combo = QComboBox()
        for key, label in TRANSFER_EVENT_LABELS.items():
            type_combo.addItem(tr(label), key)
        type_combo.currentIndexChanged.connect(lambda: self._update_transfer_row_description(row))
        table.setCellWidget(row, _T_TYPE, type_combo)

        join_team_combo = QComboBox()
        configure_mlb_team_combo(join_team_combo, self.settings, tracked_first=True)
        table.setCellWidget(row, _T_JOIN_TEAM, join_team_combo)

        counterpart_combo = QComboBox()
        configure_mlb_team_combo(counterpart_combo, self.settings)
        table.setCellWidget(row, _T_COUNTERPART, counterpart_combo)

        season_edit = QLineEdit()
        season_edit.setPlaceholderText(tr("Auto in-season"))
        table.setCellWidget(row, _T_SEASON, season_edit)

        desc_edit = QLineEdit()
        table.setCellWidget(row, _T_DESC, desc_edit)
        table.setCellWidget(row, _T_NOTES, QLineEdit())

        self._update_bulk_status()
        return row

    def _update_transfer_row_description(self, row: int) -> None:
        table = self.transfer_table
        if row >= table.rowCount():
            return
        type_combo = table.cellWidget(row, _T_TYPE)
        desc_edit = table.cellWidget(row, _T_DESC)
        joining_combo = table.cellWidget(row, _T_JOINING)
        leaving_combo = table.cellWidget(row, _T_LEAVING)
        if not all(
            isinstance(w, (QComboBox, QLineEdit))
            for w in (type_combo, desc_edit, joining_combo, leaving_combo)
        ):
            return
        if str(type_combo.currentData()) != "trade":
            return
        joining = parse_player_name_list(joining_combo.currentText().strip())
        leaving = parse_player_name_list(leaving_combo.currentText().strip())
        auto = build_trade_description(joining, leaving)
        if not desc_edit.text().strip() or desc_edit.text().strip() == desc_edit.property("_auto_text"):
            desc_edit.blockSignals(True)
            desc_edit.setText(auto)
            desc_edit.setProperty("_auto_text", auto)
            desc_edit.blockSignals(False)

    def _row_is_blank_transfer(self, row: int) -> bool:
        date_edit = self.transfer_table.cellWidget(row, _T_DATE)
        return not (isinstance(date_edit, QLineEdit) and date_edit.text().strip())

    def _ensure_transfer_trailing_row(self) -> None:
        """Guarantee at least one row exists (rows are otherwise only added by button)."""
        if self.transfer_table.rowCount() == 0:
            self._add_transfer_row()

    def _on_remove_transfer_rows(self) -> None:
        rows = sorted({index.row() for index in self.transfer_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.transfer_table.removeRow(row)
        self._ensure_transfer_trailing_row()
        self._update_bulk_status()

    def _open_single_transfer_dialog(self) -> None:
        common_date = ""
        if self.transfer_table.rowCount() > 1:
            first_date = self.transfer_table.cellWidget(0, _T_DATE)
            if isinstance(first_date, QLineEdit):
                common_date = first_date.text().strip()
        dialog = SingleTransferEntryDialog(
            self.aggregator, self.settings, self, initial_date=common_date
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.form is None:
            return
        self._populate_transfer_row_from_form(dialog.form)

    def _populate_transfer_row_from_form(self, form: ManualTransferFormData) -> None:
        row = self.transfer_table.rowCount() - 1
        if not self._row_is_blank_transfer(row):
            row = self._add_transfer_row()

        date_edit = self.transfer_table.cellWidget(row, _T_DATE)
        if isinstance(date_edit, QLineEdit):
            date_edit.blockSignals(True)
            date_edit.setText(form.achieved_date.isoformat())
            date_edit.blockSignals(False)

        joining_combo = self.transfer_table.cellWidget(row, _T_JOINING)
        if isinstance(joining_combo, QComboBox):
            joining_combo.setCurrentText(form.joining_players)
        leaving_combo = self.transfer_table.cellWidget(row, _T_LEAVING)
        if isinstance(leaving_combo, QComboBox):
            leaving_combo.setCurrentText(form.leaving_players)

        type_combo = self.transfer_table.cellWidget(row, _T_TYPE)
        if isinstance(type_combo, QComboBox):
            index = type_combo.findData(form.event_type)
            if index >= 0:
                type_combo.setCurrentIndex(index)

        join_team_combo = self.transfer_table.cellWidget(row, _T_JOIN_TEAM)
        if isinstance(join_team_combo, QComboBox) and form.join_team:
            join_team_combo.setCurrentText(form.join_team)
        counterpart_combo = self.transfer_table.cellWidget(row, _T_COUNTERPART)
        if isinstance(counterpart_combo, QComboBox) and form.counterpart_team:
            counterpart_combo.setCurrentText(form.counterpart_team)

        if form.season is not None:
            season_edit = self.transfer_table.cellWidget(row, _T_SEASON)
            if isinstance(season_edit, QLineEdit):
                season_edit.setText(str(form.season))

        desc_edit = self.transfer_table.cellWidget(row, _T_DESC)
        if isinstance(desc_edit, QLineEdit):
            desc_edit.setText(form.description)
        notes_edit = self.transfer_table.cellWidget(row, _T_NOTES)
        if isinstance(notes_edit, QLineEdit):
            notes_edit.setText(form.notes)

        self._ensure_transfer_trailing_row()
        self._update_bulk_status()

    def _collect_transfer_entries(self) -> list[ManualTransferFormData] | None:
        entries: list[ManualTransferFormData] = []
        for row in range(self.transfer_table.rowCount()):
            if self._row_is_blank_transfer(row):
                continue
            result = self._build_transfer_row_form(row)
            if result is None:
                return None
            entries.append(result)
        return entries

    def _build_transfer_row_form(self, row: int) -> ManualTransferFormData | None:
        row_label = tr("Row {n}").format(n=row + 1)
        table = self.transfer_table

        date_edit = table.cellWidget(row, _T_DATE)
        parsed = parse_flexible_date(date_edit.text() if isinstance(date_edit, QLineEdit) else "")
        if parsed is None:
            QMessageBox.warning(self, tr("Input Error"), f"{row_label}: " + tr("Check date format"))
            return None

        season_edit = table.cellWidget(row, _T_SEASON)
        season_text = season_edit.text().strip() if isinstance(season_edit, QLineEdit) else ""
        season: int | None = None
        if season_text:
            try:
                season = int(season_text)
            except ValueError:
                QMessageBox.warning(
                    self, tr("Input Error"), f"{row_label}: " + tr("Season must be a number.")
                )
                return None
        else:
            # In-season transfers derive the season from the date; off-season
            # (or unknown) transfers require an explicit season.
            season = season_if_in_season(self.aggregator.conn, parsed)
            if season is None:
                QMessageBox.warning(
                    self,
                    tr("Input Required"),
                    f"{row_label}: "
                    + tr("Off-season transfer: please enter the season directly."),
                )
                return None

        type_combo = table.cellWidget(row, _T_TYPE)
        event_type = str(type_combo.currentData()) if isinstance(type_combo, QComboBox) else ""

        join_team_combo = table.cellWidget(row, _T_JOIN_TEAM)
        join_team = join_team_combo.currentText().strip() if isinstance(join_team_combo, QComboBox) else ""
        if not join_team and event_type == "fa_contract":
            tracked = tracked_team_names(self.settings)
            if tracked:
                join_team = tracked[0]

        counterpart_combo = table.cellWidget(row, _T_COUNTERPART)
        joining_combo = table.cellWidget(row, _T_JOINING)
        leaving_combo = table.cellWidget(row, _T_LEAVING)
        desc_edit = table.cellWidget(row, _T_DESC)
        notes_edit = table.cellWidget(row, _T_NOTES)

        form = ManualTransferFormData(
            achieved_date=parsed,
            joining_players=joining_combo.currentText().strip() if isinstance(joining_combo, QComboBox) else "",
            leaving_players=leaving_combo.currentText().strip() if isinstance(leaving_combo, QComboBox) else "",
            event_type=event_type,
            join_team=join_team,
            counterpart_team=counterpart_combo.currentText().strip() if isinstance(counterpart_combo, QComboBox) else "",
            season=season,
            description=desc_edit.text().strip() if isinstance(desc_edit, QLineEdit) else "",
            notes=notes_edit.text().strip() if isinstance(notes_edit, QLineEdit) else "",
        )
        errors = validate_manual_transfer(form)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), f"{row_label}:\n" + "\n".join(errors))
            return None
        return form

    # ── Injury page ──────────────────────────────────────────────────────

    def _build_injury_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(tr("Records injury events such as player injuries and returns."))
        hint.setWordWrap(True)

        toolbar = QHBoxLayout()
        self.injury_add_row_button = QPushButton(tr("Add Row"))
        self.injury_add_row_button.clicked.connect(lambda: self._add_injury_row())
        self.injury_add_one_button = QPushButton(tr("Add One at a Time"))
        self.injury_add_one_button.clicked.connect(self._open_single_injury_dialog)
        self.injury_remove_button = QPushButton(tr("Remove Selected"))
        self.injury_remove_button.clicked.connect(self._on_remove_injury_rows)
        toolbar.addWidget(self.injury_add_row_button)
        toolbar.addWidget(self.injury_add_one_button)
        toolbar.addStretch()
        toolbar.addWidget(self.injury_remove_button)

        self.injury_table = QTableWidget(0, 8)
        self.injury_table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Player"),
                tr("Injury"),
                tr("Duration"),
                tr("Affil. Team"),
                tr("Season"),
                tr("Description"),
                tr("Notes"),
            ]
        )
        self._style_history_table(self.injury_table)
        self.injury_table.horizontalHeader().setSectionResizeMode(
            _I_DESC, QHeaderView.ResizeMode.Stretch
        )
        _scaled_column_widths(self.injury_table, {
            _I_DATE: 100, _I_PLAYER: 190, _I_LABEL: 160, _I_DURATION: 140,
            _I_TEAM: 130, _I_SEASON: 70, _I_NOTES: 160,
        })
        _mark_required_columns(self.injury_table, (_I_DATE, _I_PLAYER, _I_LABEL))

        layout.addWidget(hint)
        layout.addLayout(toolbar)
        layout.addWidget(table_card(tr("Injury"), self.injury_table), stretch=1)

        self._ensure_injury_trailing_row()
        return page

    def _add_injury_row(self) -> int:
        table = self.injury_table
        row = table.rowCount()
        table.insertRow(row)

        date_edit = QLineEdit()
        date_edit.setPlaceholderText("2026-03-01")
        table.setCellWidget(row, _I_DATE, date_edit)

        player_combo = QComboBox()
        configure_player_combo(player_combo, self.aggregator, self.settings)
        table.setCellWidget(row, _I_PLAYER, player_combo)

        label_edit = QLineEdit()
        label_edit.setPlaceholderText(tr("e.g., Hamstring, shoulder surgery"))
        label_edit.textChanged.connect(lambda: self._update_injury_row_description(row))
        table.setCellWidget(row, _I_LABEL, label_edit)

        duration_edit = QLineEdit()
        duration_edit.setPlaceholderText(tr("e.g., 3 days, 3 weeks, 5-6 months"))
        duration_edit.textChanged.connect(lambda: self._update_injury_row_description(row))
        table.setCellWidget(row, _I_DURATION, duration_edit)

        team_combo = QComboBox()
        team_combo.setEditable(False)
        self._fill_target_team_combo(team_combo)
        table.setCellWidget(row, _I_TEAM, team_combo)

        season_edit = QLineEdit()
        season_edit.setPlaceholderText(tr("Auto (date year)"))
        table.setCellWidget(row, _I_SEASON, season_edit)
        table.setCellWidget(row, _I_DESC, QLineEdit())
        table.setCellWidget(row, _I_NOTES, QLineEdit())

        self._update_bulk_status()
        return row

    def _update_injury_row_description(self, row: int) -> None:
        table = self.injury_table
        if row >= table.rowCount():
            return
        label_edit = table.cellWidget(row, _I_LABEL)
        duration_edit = table.cellWidget(row, _I_DURATION)
        desc_edit = table.cellWidget(row, _I_DESC)
        if not all(isinstance(w, QLineEdit) for w in (label_edit, duration_edit, desc_edit)):
            return
        auto = build_injury_description(label_edit.text(), duration_edit.text())
        desc_edit.blockSignals(True)
        desc_edit.setText(auto)
        desc_edit.blockSignals(False)

    def _row_is_blank_injury(self, row: int) -> bool:
        date_edit = self.injury_table.cellWidget(row, _I_DATE)
        return not (isinstance(date_edit, QLineEdit) and date_edit.text().strip())

    def _ensure_injury_trailing_row(self) -> None:
        """Guarantee at least one row exists (rows are otherwise only added by button)."""
        if self.injury_table.rowCount() == 0:
            self._add_injury_row()

    def _on_remove_injury_rows(self) -> None:
        rows = sorted({index.row() for index in self.injury_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.injury_table.removeRow(row)
        self._ensure_injury_trailing_row()
        self._update_bulk_status()

    def _open_single_injury_dialog(self) -> None:
        common_date = ""
        if self.injury_table.rowCount() > 1:
            first_date = self.injury_table.cellWidget(0, _I_DATE)
            if isinstance(first_date, QLineEdit):
                common_date = first_date.text().strip()
        dialog = SingleInjuryEntryDialog(
            self.aggregator, self.settings, self, initial_date=common_date
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.form is None:
            return
        self._populate_injury_row_from_form(dialog.form)

    def _populate_injury_row_from_form(self, form: ManualInjuryFormData) -> None:
        row = self.injury_table.rowCount() - 1
        if not self._row_is_blank_injury(row):
            row = self._add_injury_row()

        date_edit = self.injury_table.cellWidget(row, _I_DATE)
        if isinstance(date_edit, QLineEdit):
            date_edit.blockSignals(True)
            date_edit.setText(form.achieved_date.isoformat())
            date_edit.blockSignals(False)

        player_combo = self.injury_table.cellWidget(row, _I_PLAYER)
        if isinstance(player_combo, QComboBox) and form.player_name:
            player_combo.setCurrentText(form.player_name)

        label_edit = self.injury_table.cellWidget(row, _I_LABEL)
        if isinstance(label_edit, QLineEdit):
            label_edit.setText(form.injury_label)
        duration_edit = self.injury_table.cellWidget(row, _I_DURATION)
        if isinstance(duration_edit, QLineEdit):
            duration_edit.setText(form.duration)

        team_combo = self.injury_table.cellWidget(row, _I_TEAM)
        if isinstance(team_combo, QComboBox) and form.team:
            index = team_combo.findData(form.team)
            if index >= 0:
                team_combo.setCurrentIndex(index)

        if form.season is not None:
            season_edit = self.injury_table.cellWidget(row, _I_SEASON)
            if isinstance(season_edit, QLineEdit):
                season_edit.setText(str(form.season))

        desc_edit = self.injury_table.cellWidget(row, _I_DESC)
        if isinstance(desc_edit, QLineEdit):
            desc_edit.setText(form.description)
        notes_edit = self.injury_table.cellWidget(row, _I_NOTES)
        if isinstance(notes_edit, QLineEdit):
            notes_edit.setText(form.notes)

        self._ensure_injury_trailing_row()
        self._update_bulk_status()

    def _collect_injury_entries(self) -> list[ManualInjuryFormData] | None:
        entries: list[ManualInjuryFormData] = []
        for row in range(self.injury_table.rowCount()):
            if self._row_is_blank_injury(row):
                continue
            result = self._build_injury_row_form(row)
            if result is None:
                return None
            entries.append(result)
        return entries

    def _build_injury_row_form(self, row: int) -> ManualInjuryFormData | None:
        row_label = tr("Row {n}").format(n=row + 1)
        table = self.injury_table

        date_edit = table.cellWidget(row, _I_DATE)
        parsed = parse_flexible_date(date_edit.text() if isinstance(date_edit, QLineEdit) else "")
        if parsed is None:
            QMessageBox.warning(self, tr("Input Error"), f"{row_label}: " + tr("Check date format"))
            return None

        season_edit = table.cellWidget(row, _I_SEASON)
        season_text = season_edit.text().strip() if isinstance(season_edit, QLineEdit) else ""
        if season_text:
            try:
                season: int | None = int(season_text)
            except ValueError:
                QMessageBox.warning(
                    self, tr("Input Error"), f"{row_label}: " + tr("Season must be a number.")
                )
                return None
        else:
            # Blank season defaults to the year of the date.
            season = parsed.year

        player_combo = table.cellWidget(row, _I_PLAYER)
        label_edit = table.cellWidget(row, _I_LABEL)
        duration_edit = table.cellWidget(row, _I_DURATION)
        team_combo = table.cellWidget(row, _I_TEAM)
        desc_edit = table.cellWidget(row, _I_DESC)
        notes_edit = table.cellWidget(row, _I_NOTES)

        team = team_combo.currentText().strip() if isinstance(team_combo, QComboBox) else ""
        if not team:
            # Blank affiliation defaults to the topmost tracked team.
            team = first_tracked_team_name(self.settings)

        form = ManualInjuryFormData(
            player_name=canonical_player_text(player_combo) if isinstance(player_combo, QComboBox) else "",
            achieved_date=parsed,
            injury_label=label_edit.text().strip() if isinstance(label_edit, QLineEdit) else "",
            duration=duration_edit.text().strip() if isinstance(duration_edit, QLineEdit) else "",
            team=team,
            season=season,
            description=desc_edit.text().strip() if isinstance(desc_edit, QLineEdit) else "",
            notes=notes_edit.text().strip() if isinstance(notes_edit, QLineEdit) else "",
        )
        errors = validate_manual_injury(form)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), f"{row_label}:\n" + "\n".join(errors))
            return None
        return form

    # ── Shared ───────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        if index in (_TAB_MILESTONE, _TAB_AWARD):
            self.stack.setCurrentIndex(0)
            # Games count is only mandatory for milestones, not for awards.
            _set_header_required(self.milestone_table, _M_GAMES, index == _TAB_MILESTONE)
            self._refresh_milestone_pool_for_all_rows()
        elif index == _TAB_TRANSFER:
            self.stack.setCurrentIndex(1)
        elif index == _TAB_INJURY:
            self.stack.setCurrentIndex(2)
        self._update_bulk_status()

    def _bulk_entry_count(self) -> int:
        tab = self.tabs.currentIndex()
        if tab in (_TAB_MILESTONE, _TAB_AWARD):
            return sum(
                0 if self._row_is_blank_milestone(row) else 1
                for row in range(self.milestone_table.rowCount())
            )
        if tab == _TAB_TRANSFER:
            return sum(
                0 if self._row_is_blank_transfer(row) else 1
                for row in range(self.transfer_table.rowCount())
            )
        return sum(
            0 if self._row_is_blank_injury(row) else 1
            for row in range(self.injury_table.rowCount())
        )

    def _update_bulk_status(self) -> None:
        if not hasattr(self, "bulk_status_label"):
            return
        if self.mode_stack.currentWidget() is self.single_mode_page:
            return
        count = self._bulk_entry_count()
        self.bulk_status_label.setText(
            tr("Bulk mode: {count} record(s) ready to validate and save. Row errors are shown before saving.").format(
                count=count
            )
        )

    def add_extracted_milestone(
        self, form: ManualMilestoneFormData, milestone: MilestoneDefinition
    ) -> None:
        """Reusable entry point for message extraction review screens."""
        self.tabs.setCurrentIndex(_TAB_AWARD if self._is_award_milestone(milestone) else _TAB_MILESTONE)
        self._show_bulk_mode()
        self._populate_milestone_row_from_form(form, milestone)

    def add_extracted_transfer(self, form: ManualTransferFormData) -> None:
        """Reusable entry point for message extraction review screens."""
        self.tabs.setCurrentIndex(_TAB_TRANSFER)
        self._show_bulk_mode()
        self._populate_transfer_row_from_form(form)

    def add_extracted_injury(self, form: ManualInjuryFormData) -> None:
        """Reusable entry point for message extraction review screens."""
        self.tabs.setCurrentIndex(_TAB_INJURY)
        self._show_bulk_mode()
        self._populate_injury_row_from_form(form)

    def create_guided_form_for_extracted(self, forms: list[object]) -> GuidedMilestoneForm:
        """Shared guided editor used by message extraction review dialogs."""
        return GuidedMilestoneForm(
            forms,
            intro=tr("Review and correct only the fields needed for this record."),
            parent=self,
            aggregator=self.aggregator,
            settings=self.settings,
            milestones=self.milestones,
        )

    @staticmethod
    def _is_award_milestone(milestone: MilestoneDefinition) -> bool:
        key = str(milestone.key).lower()
        label = str(milestone.label).lower()
        return "award" in key or "award" in label or "수상" in label

    def _checker(self) -> MilestoneChecker:
        return MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )

    def _on_accept(self) -> None:
        tab = self.tabs.currentIndex()
        checker = self._checker()

        if tab in (_TAB_MILESTONE, _TAB_AWARD):
            entries = self._collect_milestone_entries()
            if entries is None:
                return
            if not entries:
                QMessageBox.warning(
                    self, tr("Input Required"), tr("Please add at least one record.")
                )
                return
            for form, milestone in entries:
                dup_kind, dup_msg = check_duplicate(self.aggregator.conn, form, milestone)
                if dup_kind == "warn":
                    reply = QMessageBox.question(
                        self,
                        tr("Duplicate Check"),
                        tr("{dup_msg}\nAdd anyway?").format(dup_msg=dup_msg),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        continue
                checker.record_manual_milestone(form)
            self.accept()
            return

        if tab == _TAB_TRANSFER:
            entries = self._collect_transfer_entries()
            if entries is None:
                return
            if not entries:
                QMessageBox.warning(
                    self, tr("Input Required"), tr("Please add at least one record.")
                )
                return
            for form in entries:
                try:
                    checker.record_manual_transfer(form)
                except ValueError as exc:
                    QMessageBox.warning(self, tr("Input Error"), str(exc))
                    return
            self.accept()
            return

        if tab == _TAB_INJURY:
            entries = self._collect_injury_entries()
            if entries is None:
                return
            if not entries:
                QMessageBox.warning(
                    self, tr("Input Required"), tr("Please add at least one record.")
                )
                return
            for form in entries:
                try:
                    checker.record_manual_injury(form)
                except ValueError as exc:
                    QMessageBox.warning(self, tr("Input Error"), str(exc))
                    return
            self.accept()
            return
