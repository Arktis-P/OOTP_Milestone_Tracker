"""Roster rating edit tab — per-player dialog on double-click."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, resolve_data_path
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.roster.editor import RosterEditor, RosterFilter
from core.roster.korean_names import KoreanNameMapper, load_korean_name_mapper
from core.roster.ootp_format import player_age, player_display_name
from core.roster.paths import (
    RosterLeague,
    expected_roster_path,
    find_roster_file,
    roster_export_label,
)
from core.roster.position_filter import POSITION_GROUP_OPTIONS, position_label
from core.roster.row_access import row_get
from gui.widgets.bulk_rating_dialog import BulkRatingDialog
from gui.widgets.player_rating_dialog import PlayerRatingDialog
from gui.widgets.table_widgets import NumericSortItem, TablePanel
from gui.widgets.card_panel import CardPanel, section_label

_LEAGUE_ITEMS: list[tuple[str, RosterLeague]] = [
    ("MLB", "mlb"),
    ("KBO", "kbo"),
]

def _table_columns() -> list[str]:
    return [tr("Name"), tr("Korean Name"), tr("Team"), tr("League"), tr("Position"), tr("Age"), "CON", "POW", "STU"]

_NUMERIC_COLUMNS = {5, 6, 7, 8}


class RosterView(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.editor = RosterEditor()
        self.editor.set_season_year(settings.current_season)
        self._filtered_rows: list[list[str]] = []
        self._loaded_path: Path | None = None
        self._current_league: RosterLeague = "mlb"

        self.league_combo = QComboBox()
        for label, league in _LEAGUE_ITEMS:
            self.league_combo.addItem(label, league)
        self.league_combo.currentIndexChanged.connect(self._on_league_changed)

        self.path_label = QLabel(tr("File: (none)"))
        self.reload_button = QPushButton(tr("Load"))
        self.reload_button.clicked.connect(lambda: self._reload_file(show_warning=True))

        self.position_combo = QComboBox()
        for label, group_key in POSITION_GROUP_OPTIONS:
            self.position_combo.addItem(label, group_key)

        self.min_age_input = QSpinBox()
        self.max_age_input = QSpinBox()
        for spin in (self.min_age_input, self.max_age_input):
            spin.setRange(0, 60)
            spin.setSpecialValueText(tr("All"))
            spin.setValue(0)

        self.bulk_button = QPushButton(tr("Bulk Edit..."))
        self.bulk_button.clicked.connect(self._open_bulk_dialog)

        self.backup_button = QPushButton(tr("Save Backup"))
        self.save_button = QPushButton(tr("Save"))
        self.save_button.setObjectName("primaryButton")
        self.save_button.setEnabled(False)
        self.backup_button.clicked.connect(self.save_backup)
        self.save_button.clicked.connect(self.save_file)

        filter_button = QPushButton(tr("Apply Filter"))
        filter_button.clicked.connect(self.apply_filter)

        self.table_panel = TablePanel(
            _table_columns(),
            placeholder=tr("Search player..."),
        )
        self.table_panel.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.info_label = QLabel(
            tr(
                "Loads roster from the save's import_export folder. "
                "Double-click a player to edit ratings."
            )
        )
        self.info_label.setObjectName("mutedLabel")
        self.info_label.setWordWrap(True)

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        source_row.addWidget(section_label(tr("League")))
        source_row.addWidget(self.league_combo)
        source_row.addWidget(self.path_label, stretch=1)
        source_row.addWidget(self.reload_button)

        filter_form = QFormLayout()
        filter_form.addRow(tr("Position"), self.position_combo)
        filter_form.addRow(tr("Min Age"), self.min_age_input)
        filter_form.addRow(tr("Max Age"), self.max_age_input)

        action_row = QHBoxLayout()
        action_row.addWidget(filter_button)
        action_row.addWidget(self.bulk_button)
        action_row.addStretch()
        action_row.addWidget(self.backup_button)
        action_row.addWidget(self.save_button)

        toolbar_card = CardPanel(tr("Rating Editor"))
        toolbar_card.content_layout.addLayout(source_row)
        toolbar_card.content_layout.addLayout(filter_form)
        toolbar_card.content_layout.addLayout(action_row)
        toolbar_card.content_layout.addWidget(self.info_label)

        table_card = CardPanel(tr("Roster List"))
        table_card.add_widget(self.table_panel)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(toolbar_card)
        layout.addWidget(table_card, stretch=1)

        self._reload_file(show_warning=False)

    def _import_export_dir(self) -> Path | None:
        directory = self.settings.import_export_dir or self.settings.initial_stats_dir
        if not directory:
            return None
        return Path(directory)

    def _on_league_changed(self) -> None:
        league = self.league_combo.currentData()
        if league:
            self._current_league = league
        self._reload_file(show_warning=True)

    def _resolve_roster_path(self) -> Path | None:
        export_dir = self._import_export_dir()
        return find_roster_file(export_dir, self._current_league)

    def _expected_path_display(self) -> str:
        export_dir = self._import_export_dir()
        if export_dir is None:
            return tr("(No save configured)")
        return str(expected_roster_path(export_dir, self._current_league))

    def _optional_age(self, spin: QSpinBox) -> int | None:
        return spin.value() or None

    def _build_filter(self) -> RosterFilter:
        return RosterFilter(
            position_group=self.position_combo.currentData(),
            min_age=self._optional_age(self.min_age_input),
            max_age=self._optional_age(self.max_age_input),
            season_year=self.settings.current_season,
        )

    def _reload_file(self, *, show_warning: bool = True) -> None:
        export_dir = self._import_export_dir()
        if export_dir is None:
            self._loaded_path = None
            self.path_label.setText(tr("File: (no save configured)"))
            if show_warning:
                QMessageBox.warning(
                    self,
                    tr("File Not Found"),
                    tr("No active save is configured.\nSelect a league in the Settings tab."),
                )
            return

        path = self._resolve_roster_path()
        self.path_label.setText(
            tr("File: {path}").format(path=path)
            if path
            else tr("File: {path}").format(path=self._expected_path_display())
        )
        if path is None:
            self._loaded_path = None
            if show_warning:
                label = roster_export_label(self._current_league)
                QMessageBox.warning(
                    self,
                    tr("File Not Found"),
                    tr(
                        "Roster file not found.\n\n"
                        "Path: {path}\n"
                        "({label} — OOTP roster export required in import_export folder)"
                    ).format(
                        path=expected_roster_path(export_dir, self._current_league),
                        label=label,
                    ),
                )
            return

        try:
            self.editor.set_season_year(self.settings.current_season)
            self.editor.load(path)
        except Exception as exc:
            self._loaded_path = None
            QMessageBox.critical(self, tr("Load Failed"), str(exc))
            return

        self._loaded_path = path
        self.save_button.setEnabled(False)
        self.info_label.setText(
            tr("Loaded: {name} ({count:,} players)").format(
                name=path.name, count=self.editor.row_count
            )
        )
        self._filtered_rows = self.editor.filter_rows(self._build_filter())
        self._show_rows(self._filtered_rows)

    def apply_filter(self) -> None:
        if not self.editor.row_count:
            QMessageBox.warning(self, tr("No Data"), tr("Please load the roster first."))
            return
        self._filtered_rows = self.editor.filter_rows(self._build_filter())
        self.info_label.setText(
            tr("Filter result: {count:,} players").format(count=len(self._filtered_rows))
        )
        self._show_rows(self._filtered_rows)

    def _open_bulk_dialog(self) -> None:
        export_dir = self._import_export_dir()
        if export_dir is None:
            QMessageBox.warning(
                self,
                tr("No Save Configured"),
                tr("No active save is configured."),
            )
            return
        try:
            with Aggregator(resolve_data_path(self.settings.db_path)) as agg:
                dialog = BulkRatingDialog(
                    agg,
                    str(export_dir),
                    self.settings,
                    parent=self,
                )
        except FileNotFoundError as exc:
            QMessageBox.warning(self, tr("File Not Found"), str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, tr("Roster Error"), str(exc))
            return
        dialog.exec()

    def _on_row_double_clicked(self, row_index: int, _column: int) -> None:
        item = self.table_panel.table.item(row_index, 0)
        if item is None:
            return
        data_index = item.data(Qt.ItemDataRole.UserRole)
        if data_index is None:
            return
        data_index = int(data_index)
        if data_index < 0 or data_index >= len(self._filtered_rows):
            return
        player_row = self._filtered_rows[data_index]
        dialog = PlayerRatingDialog(
            player_row,
            self.editor.fieldnames,
            season_year=self.settings.current_season,
            parent=self,
        )
        if dialog.exec():
            self._show_rows(self._filtered_rows)

    def save_backup(self) -> None:
        if not self._loaded_path:
            QMessageBox.warning(self, tr("File Not Found"), tr("No original file to back up."))
            return
        try:
            backup = self.editor.save_copy(self._loaded_path)
        except Exception as exc:
            QMessageBox.critical(self, tr("Backup Failed"), str(exc))
            return
        self.save_button.setEnabled(True)
        QMessageBox.information(
            self, tr("Backup Complete"), tr("Copy saved:\n{path}").format(path=backup)
        )

    def save_file(self) -> None:
        if not self.editor.backup_saved:
            reply = QMessageBox.question(
                self,
                tr("Confirm Backup"),
                tr("No backup has been saved yet.\nCreate a backup now before saving?"),
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.save_backup()
        target = self._loaded_path
        if target is None:
            return
        try:
            saved = self.editor.save(target)
        except Exception as exc:
            QMessageBox.critical(self, tr("Save Failed"), str(exc))
            return
        QMessageBox.information(
            self, tr("Saved"), tr("Saved to: {path}").format(path=saved)
        )

    def _show_rows(self, rows: list[list[str]]) -> None:
        fieldnames = self.editor.fieldnames
        season = self.settings.current_season
        mapper = load_korean_name_mapper()
        display_rows = []
        for row in rows[:5000]:
            age = player_age(row, season_year=season, fieldnames=fieldnames)
            last_name = row_get(row, fieldnames, "LastName").strip()
            first_name = row_get(row, fieldnames, "FirstName").strip()
            nation = row_get(row, fieldnames, "Nation").strip()
            korean_name = mapper.format_player_name(
                last_name,
                first_name,
                western_order=KoreanNameMapper.uses_western_name_order(nation),
            )
            display_rows.append(
                [
                    player_display_name(row, fieldnames),
                    korean_name,
                    row_get(row, fieldnames, "Team Name"),
                    row_get(row, fieldnames, "League Name"),
                    position_label(row_get(row, fieldnames, "Position")),
                    "" if age is None else str(age),
                    row_get(row, fieldnames, "Contact vL"),
                    row_get(row, fieldnames, "Power vL"),
                    row_get(row, fieldnames, "Stuff Overall"),
                ]
            )
        table = self.table_panel.table
        table.setSortingEnabled(False)
        table.setRowCount(len(display_rows))
        for row_idx, values in enumerate(display_rows):
            for col_idx, value in enumerate(values):
                text = "" if value is None else str(value)
                if col_idx in _NUMERIC_COLUMNS:
                    try:
                        sort_value = float(text) if text else -1.0
                    except ValueError:
                        sort_value = -1.0
                    cell: QTableWidgetItem = NumericSortItem(text, sort_value)
                else:
                    cell = QTableWidgetItem(text)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row_idx)
                table.setItem(row_idx, col_idx, cell)
        table.setSortingEnabled(True)
        if len(rows) > 5000:
            self.info_label.setText(
                f"{self.info_label.text()} {tr('(display limit: 5,000 players)')}"
            )
