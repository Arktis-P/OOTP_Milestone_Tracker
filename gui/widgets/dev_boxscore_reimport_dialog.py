"""Dev tool: pick and re-import a single box score file."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from core.config import AppSettings, SettingsManager, resolve_data_path
from core.i18n import tr
from core.milestone.definitions import load_milestones
from core.parser.boxscore_html import (
    BoxscoreFileSummary,
    list_boxscore_summaries,
    summarize_boxscore_file,
)
from core.stats.aggregator import Aggregator
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import (
    add_dialog_footer,
    init_dialog_layout,
    make_button_box,
    muted_label,
    style_primary_button,
    table_card,
    toolbar_row,
)
from gui.theme import RED_TEXT
from gui.workers.import_worker import ImportFinishedPayload
from gui.workers.reimport_worker import ReimportBoxscoreWorker


class DevBoxscoreReimportDialog(QDialog):
    def __init__(
        self,
        *,
        settings_manager: SettingsManager,
        settings: AppSettings,
        db_path: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.settings = settings
        self.db_path = db_path
        self._summaries: list[BoxscoreFileSummary] = []
        self._scan_dir = Path(settings.boxscore_dir) if settings.boxscore_dir else None
        self._worker: ReimportBoxscoreWorker | None = None
        self.result_message = ""

        self.setWindowTitle(tr("Re-import Boxscores (Dev)"))
        self.resize(*scale_size(820, 1300))

        intro = muted_label(
            tr(
                "Select a boxscore HTML file to re-import. "
                "Games already in the DB will be deleted and re-parsed. "
                "(Streak state may differ from a full season reprocess.)"
            )
        )

        self.dir_label = muted_label("", wrap=True)

        self.load_button = QPushButton(tr("Load List"))
        self.load_button.clicked.connect(self._load_from_current_dir)
        self.browse_dir_button = QPushButton(tr("Select Folder..."))
        self.browse_dir_button.clicked.connect(self._browse_directory)
        self.add_file_button = QPushButton(tr("Add Files..."))
        self.add_file_button.clicked.connect(self._add_files)
        load_row = toolbar_row(
            self.load_button,
            self.browse_dir_button,
            self.add_file_button,
        )

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [tr("Date"), tr("Away @ Home"), tr("Game ID"), tr("Filename"), "DB"]
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_reimport_button)

        self.status_label = muted_label("", wrap=True)

        self.reimport_button = QPushButton(tr("Re-import Selected Game"))
        self.reimport_button.setEnabled(False)
        self.reimport_button.clicked.connect(self._reimport_selected)
        style_primary_button(self.reimport_button)

        action_row = QHBoxLayout()
        action_row.addWidget(self.reimport_button)
        action_row.addStretch()

        buttons = make_button_box(close=True, cancel=False)

        table_panel = table_card(tr("Boxscore Files"), self.table)

        layout = init_dialog_layout(self)
        layout.addWidget(intro)
        layout.addWidget(self.dir_label)
        layout.addWidget(load_row)
        layout.addWidget(table_panel, stretch=1)
        layout.addWidget(self.status_label)
        layout.addLayout(action_row)
        add_dialog_footer(layout, buttons)
        buttons.rejected.connect(self.reject)

        self._refresh_dir_label()
        if self._scan_dir and self._scan_dir.is_dir():
            self._load_from_current_dir()

    def _refresh_dir_label(self) -> None:
        if self._scan_dir and str(self._scan_dir):
            self.dir_label.setText(tr("Scan folder: {path}").format(path=self._scan_dir))
        else:
            self.dir_label.setText(
                tr("Scan folder: (no boxscore folder configured — select a folder or file)")
            )

    def _known_game_ids(self) -> set[int]:
        try:
            with Aggregator(self.db_path) as aggregator:
                return aggregator.get_known_game_ids()
        except Exception:
            return set()

    def _populate_table(self, summaries: list[BoxscoreFileSummary]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(summaries))
        for row, item in enumerate(summaries):
            match = self._format_match(item)
            db_status = tr("Imported") if item.already_imported else "—"
            values = (
                item.date or "—",
                match,
                str(item.game_id),
                item.path.name,
                db_status,
            )
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col == 2:
                    cell.setData(Qt.ItemDataRole.UserRole, item.game_id)
                if col == 4 and item.already_imported:
                    cell.setForeground(QColor(RED_TEXT))
                self.table.setItem(row, col, cell)
            self.table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, str(item.path)
            )
        self.table.setSortingEnabled(True)
        self.status_label.setText(tr("{count} files").format(count=len(summaries)))

    @staticmethod
    def _format_match(item: BoxscoreFileSummary) -> str:
        if item.away_team and item.home_team:
            return f"{item.away_team} @ {item.home_team}"
        if item.away_team or item.home_team:
            return f"{item.away_team or '?'} @ {item.home_team or '?'}"
        return "—"

    def _merge_summaries(self, new_items: list[BoxscoreFileSummary]) -> None:
        by_path = {str(item.path.resolve()): item for item in self._summaries}
        for item in new_items:
            by_path[str(item.path.resolve())] = item
        self._summaries = sorted(
            by_path.values(),
            key=lambda row: (row.date, row.game_id, row.path.name),
        )
        self._populate_table(self._summaries)

    def _load_from_current_dir(self) -> None:
        if not self._scan_dir or not self._scan_dir.is_dir():
            QMessageBox.warning(
                self,
                tr("Folder Not Found"),
                tr("Select a boxscore folder first, or verify the league path in settings."),
            )
            return
        known = self._known_game_ids()
        items = list_boxscore_summaries(self._scan_dir, known_game_ids=known)
        self._summaries = items
        self._populate_table(items)

    def _browse_directory(self) -> None:
        start = str(self._scan_dir) if self._scan_dir else ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("Select Boxscore Folder"),
            start,
        )
        if not chosen:
            return
        self._scan_dir = Path(chosen)
        self._refresh_dir_label()
        self._load_from_current_dir()

    def _add_files(self) -> None:
        start = str(self._scan_dir) if self._scan_dir else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("Select Boxscore HTML"),
            start,
            "Box score (*.html);;All files (*)",
        )
        if not paths:
            return
        known = self._known_game_ids()
        items: list[BoxscoreFileSummary] = []
        for path_str in paths:
            item = summarize_boxscore_file(path_str, known_game_ids=known)
            if item is None:
                QMessageBox.warning(
                    self,
                    tr("File Format"),
                    tr("Not a game_box_*.html file: {filename}").format(
                        filename=Path(path_str).name
                    ),
                )
                continue
            items.append(item)
        if items:
            self._merge_summaries(items)

    def _selected_summary(self) -> BoxscoreFileSummary | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        path_item = self.table.item(row, 0)
        if path_item is None:
            return None
        path_str = path_item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return None
        resolved = str(Path(str(path_str)).resolve())
        for item in self._summaries:
            if str(item.path.resolve()) == resolved:
                return item
        return None

    def _update_reimport_button(self) -> None:
        enabled = (
            self._selected_summary() is not None and self._worker is None
        )
        self.reimport_button.setEnabled(enabled)

    def _set_busy(self, busy: bool) -> None:
        self.load_button.setEnabled(not busy)
        self.browse_dir_button.setEnabled(not busy)
        self.add_file_button.setEnabled(not busy)
        self.table.setEnabled(not busy)
        if not busy:
            self._update_reimport_button()
        else:
            self.reimport_button.setEnabled(False)

    def _reimport_selected(self) -> None:
        selected = self._selected_summary()
        if selected is None:
            return

        answer = QMessageBox.question(
            self,
            tr("Confirm Re-import"),
            tr(
                "The following game will be re-imported.\n\n"
                "{match}\n"
                "Date: {date}\n"
                "File: {filename}\n\n"
                "Existing DB data and milestone records for this game will be deleted and reprocessed."
            ).format(
                match=self._format_match(selected),
                date=selected.date or "—",
                filename=selected.path.name,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        milestones_path = resolve_data_path(self.settings.milestones_path)
        milestones = load_milestones(milestones_path)

        self._set_busy(True)
        self.status_label.setText(tr("Processing: {filename}").format(filename=selected.path.name))

        self._worker = ReimportBoxscoreWorker(
            db_path=self.db_path,
            settings_manager=self.settings_manager,
            milestones=milestones,
            settings=self.settings,
            filepath=selected.path,
            season=self.settings.current_season,
            parent=self,
        )
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._on_reimport_finished)
        self._worker.error.connect(self._on_reimport_error)
        self._worker.start()

    def _on_reimport_finished(self, payload: ImportFinishedPayload) -> None:
        self._worker = None
        self._set_busy(False)

        batch = payload.batch
        if batch.errors:
            err = batch.errors[0]
            QMessageBox.critical(
                self,
                tr("Re-import Failed"),
                err.error or tr("Unknown error"),
            )
            self.status_label.setText(tr("Re-import failed"))
            return

        parts: list[str] = []
        if batch.imported:
            parts.append(tr("Game re-imported successfully"))
        elif batch.skipped:
            parts.append(tr("Skipped (unexpected state)"))
        if payload.milestones_recorded:
            parts.append(
                tr("{count} milestone(s) recorded").format(count=payload.milestones_recorded)
            )
        self.result_message = " · ".join(parts) or tr("Re-import complete")
        self.status_label.setText(self.result_message)

        known = self._known_game_ids()
        self._summaries = [
            BoxscoreFileSummary(
                path=item.path,
                game_id=item.game_id,
                away_team=item.away_team,
                home_team=item.home_team,
                date=item.date,
                is_mlb=item.is_mlb,
                already_imported=item.game_id in known,
            )
            for item in self._summaries
        ]
        self._populate_table(self._summaries)

        QMessageBox.information(self, tr("Re-import Complete"), self.result_message)

    def _on_reimport_error(self, message: str) -> None:
        self._worker = None
        self._set_busy(False)
        self.status_label.setText(tr("Re-import failed"))
        QMessageBox.critical(self, tr("Re-import Failed"), message)
