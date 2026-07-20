"""Dialog to translate pending roman name parts into Korean mappings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.roster.gemini_korean import GeminiTranslationResult
from core.roster.korean_names import KoreanNameStore, PendingName, pending_full_name_label
from core.roster.korean_name_suggest import suggest_korean_name
from gui.theme import TEXT_MUTED, TEXT_PRIMARY
from gui.ui_compact import scale_size
from gui.utils.file_open import open_path_in_default_app
from gui.widgets.app_dialog import (
    init_dialog_layout,
    make_button_box,
    muted_label,
    style_primary_button,
    summary_label,
    table_card,
)

SUGGESTION_ROLE = Qt.ItemDataRole.UserRole + 1
_PENDING_ITEM_ROLE = Qt.ItemDataRole.UserRole


class GeminiResultDialog(QDialog):
    """Popup showing Gemini-proposed Korean translations for pending names."""

    def __init__(
        self,
        results: dict[tuple[str, str], str],
        pending: list[PendingName],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Gemini Korean Translation Results"))
        self.resize(*scale_size(720, 600))
        self._results: dict[tuple[str, str], str] = dict(results)

        intro = muted_label(
            tr(
                "Review and edit the Gemini-proposed Korean names below.\n"
                "Click 'Apply to Table' to fill them into the mapping dialog."
            )
        )

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [tr("Type"), tr("Romanized"), tr("Korean (Gemini)")]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 160)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._populate(pending, results)

        apply_button = QPushButton(tr("Apply to Table"))
        apply_button.clicked.connect(self.accept)
        style_primary_button(apply_button)

        close_box = make_button_box(close=True, cancel=False)
        close_box.rejected.connect(self.reject)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(apply_button)
        footer.addWidget(close_box)

        layout = init_dialog_layout(self)
        layout.addWidget(intro)
        layout.addWidget(table_card(tr("Translation Preview"), self.table), stretch=1)
        layout.addLayout(footer)

    def _populate(
        self,
        pending: list[PendingName],
        results: dict[tuple[str, str], str],
    ) -> None:
        rows = [(item, results.get((item.part, item.name), "")) for item in pending]
        self.table.setRowCount(len(rows))
        for row_idx, (item, korean) in enumerate(rows):
            type_item = QTableWidgetItem(tr("Last") if item.part == "last" else tr("First"))
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            type_item.setData(_PENDING_ITEM_ROLE, item)
            self.table.setItem(row_idx, 0, type_item)

            roman_item = QTableWidgetItem(item.name)
            roman_item.setFlags(roman_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 1, roman_item)

            korean_item = QTableWidgetItem(korean)
            if not korean:
                korean_item.setForeground(QColor(TEXT_MUTED))
                korean_item.setToolTip(tr("Gemini did not return a translation for this name."))
            self.table.setItem(row_idx, 2, korean_item)

    def get_translations(self) -> dict[tuple[str, str], str]:
        """Return {(part, roman): korean} from the edited table rows."""
        result: dict[tuple[str, str], str] = {}
        for row_idx in range(self.table.rowCount()):
            type_item = self.table.item(row_idx, 0)
            korean_item = self.table.item(row_idx, 2)
            if type_item is None or korean_item is None:
                continue
            pending = type_item.data(_PENDING_ITEM_ROLE)
            if not isinstance(pending, PendingName):
                continue
            korean = korean_item.text().strip()
            if korean:
                result[(pending.part, pending.name)] = korean
        return result


class KoreanNameMappingDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        api_key: str = "",
        model_preference: str = "gemini-3.5-flash",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Korean Name Mapping"))
        self.resize(*scale_size(1440, 1300))
        self._store = KoreanNameStore.load()
        self._updating_table = False
        self._api_key = api_key
        self._model_preference = model_preference

        intro = muted_label(
            tr(
                "Unregistered names from boxscore/stats imports accumulate here.\n"
                "Maps first/last names based on OOTP full name (First Last) format. "
                "Korean players show in Last+First order; others in First+Last.\n"
                "Gray suggestions are auto-proposed from bundle/user CSV mappings and "
                "MLB transliteration rules. Leave as-is and save to apply; delete to exclude."
            )
        )

        self.summary_label = summary_label()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("Search romanized..."))
        self.search_input.textChanged.connect(self._reload_table)

        self.refresh_button = QPushButton(tr("Refresh List"))
        self.refresh_button.clicked.connect(self._reload_table)

        csv_row = QHBoxLayout()
        csv_row.setSpacing(8)
        csv_row.addWidget(muted_label(tr("Edit CSV:"), wrap=False))
        self._csv_buttons: list[tuple[str, Path]] = []
        for label, filename in (
            (tr("Last Name CSV"), "korean_last_names.csv"),
            (tr("First Name CSV"), "korean_first_names.csv"),
            (tr("Pending List CSV"), "korean_names_pending.csv"),
        ):
            button = QPushButton(label)
            path = self._store.data_dir / filename
            button.clicked.connect(lambda _checked=False, p=path: self._open_csv(p))
            csv_row.addWidget(button)
            self._csv_buttons.append((label, path))
        csv_row.addStretch()

        self.gemini_button = QPushButton(tr("Translate via Gemini"))
        self.gemini_button.clicked.connect(self._translate_with_gemini)
        self.gemini_button.setEnabled(bool(api_key))
        self.gemini_check_button = QPushButton(tr("Check Gemini Connection"))
        self.gemini_check_button.clicked.connect(self._check_gemini_connection)
        self.gemini_check_button.setEnabled(bool(api_key))
        if not api_key:
            self.gemini_button.setToolTip(tr("Set Gemini API key in Settings first."))

        self.gemini_status_label = QLabel("")
        self.gemini_status_label.setStyleSheet(f"color: {TEXT_MUTED};")
        self.gemini_status_label.hide()
        self.cancel_gemini_button = QPushButton(tr("Cancel Gemini"))
        self.cancel_gemini_button.clicked.connect(self._cancel_gemini)
        self.cancel_gemini_button.hide()
        self._gemini_worker = None
        self._gemini_diagnostic_worker = None
        self._gemini_pending: list[PendingName] = []

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [tr("Type"), tr("Full Name (Ref)"), tr("Romanized"), tr("Korean Name (Suggestion)"), tr("Source")]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 180)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)

        save_button = QPushButton(tr("Save Entered Items"))
        save_button.clicked.connect(self._save_entries)
        style_primary_button(save_button)

        buttons = make_button_box(close=True, cancel=False)
        buttons.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self.summary_label, stretch=1)
        top_row.addWidget(self.search_input, stretch=1)
        top_row.addWidget(self.refresh_button)
        top_row.addWidget(self.gemini_button)
        top_row.addWidget(self.gemini_check_button)
        top_row.addWidget(self.gemini_status_label)
        top_row.addWidget(self.cancel_gemini_button)

        table_panel = table_card(tr("Pending Mappings"), self.table)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(save_button)
        footer.addWidget(buttons)

        layout = init_dialog_layout(self)
        layout.addWidget(intro)
        layout.addLayout(csv_row)
        layout.addLayout(top_row)
        layout.addWidget(table_panel, stretch=1)
        layout.addLayout(footer)

        self._reload_table()

    def _open_csv(self, path: Path) -> None:
        if not path.is_file():
            QMessageBox.warning(
                self,
                tr("File Not Found"),
                tr("CSV file not found.\n{path}").format(path=path),
            )
            return
        if not open_path_in_default_app(path):
            QMessageBox.warning(
                self,
                tr("Open Failed"),
                tr("Could not open CSV with default app.\nPath: {path}").format(path=path),
            )

    def _reload_table(self) -> None:
        self._store = KoreanNameStore.load()
        needle = self.search_input.text().strip().casefold()
        rows = self._store.pending
        if needle:
            rows = [row for row in rows if needle in row.name.casefold()]

        suggested_count = 0
        self._updating_table = True
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            for row_idx, item in enumerate(rows):
                self.table.setItem(
                    row_idx, 0, self._read_only_item(self._part_label(item.part))
                )
                self.table.setItem(
                    row_idx, 1, self._read_only_item(pending_full_name_label(item))
                )
                name_item = self._read_only_item(item.name)
                name_item.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row_idx, 2, name_item)

                suggestion = suggest_korean_name(item.part, item.name)
                korean_item = QTableWidgetItem(suggestion)
                if suggestion:
                    suggested_count += 1
                    korean_item.setData(SUGGESTION_ROLE, suggestion)
                    self._style_korean_cell(korean_item, is_recommendation=True)
                self.table.setItem(row_idx, 3, korean_item)
                self.table.setItem(row_idx, 4, self._read_only_item(item.source or "-"))
        finally:
            self.table.blockSignals(False)
            self._updating_table = False

        summary = tr("Korean name needed: {count:,}").format(count=self._store.pending_count())
        if suggested_count:
            summary += tr(" · Suggested: {count:,}").format(count=suggested_count)
        if needle:
            summary += tr(" · Showing: {count:,}").format(count=len(rows))
        self.summary_label.setText(summary)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table or item.column() != 3:
            return
        suggestion = item.data(SUGGESTION_ROLE)
        text = item.text().strip()
        if not text:
            item.setToolTip("")
            item.setForeground(QColor(TEXT_PRIMARY))
            return
        is_recommendation = bool(suggestion and text == suggestion)
        self._style_korean_cell(item, is_recommendation=is_recommendation)

    @staticmethod
    def _style_korean_cell(item: QTableWidgetItem, *, is_recommendation: bool) -> None:
        if is_recommendation:
            item.setForeground(QColor(TEXT_MUTED))
            item.setToolTip(
                tr("Auto-suggested. Save without editing to apply to mappings.")
            )
        else:
            item.setForeground(QColor(TEXT_PRIMARY))
            item.setToolTip(tr("Manually entered."))

    @staticmethod
    def _part_label(part: str) -> str:
        return tr("Last") if part == "last" else tr("First")

    @staticmethod
    def _read_only_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _translate_with_gemini(self) -> None:
        from gui.workers.gemini_worker import GeminiTranslateWorker

        self._store = KoreanNameStore.load()
        pending = self._store.pending
        if not pending:
            QMessageBox.information(self, tr("No Items"), tr("No pending names to translate."))
            return

        items = [(item.part, item.name) for item in pending]  # type: ignore[misc]

        self._gemini_pending = pending
        self.gemini_button.setEnabled(False)
        self.gemini_status_label.setText(tr("Translating via Gemini..."))
        self.gemini_status_label.show()
        self.cancel_gemini_button.show()

        worker = GeminiTranslateWorker(
            self._api_key,
            items,
            self,
            model_preference=self._model_preference,
        )
        worker.status.connect(self.gemini_status_label.setText)
        worker.finished.connect(self._on_gemini_finished)
        worker.error.connect(self._on_gemini_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._gemini_worker = worker
        worker.start()

    def _cancel_gemini(self) -> None:
        if self._gemini_worker is not None:
            self._gemini_worker.cancel()
            self.gemini_status_label.setText(tr("Cancelling Gemini request..."))
            self.cancel_gemini_button.setEnabled(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        # These QThreads are parented to this dialog; closing while one is
        # still running would otherwise destroy a live thread. Cancel and
        # wait (bounded by the SDK's own request timeout) before closing.
        if self._gemini_worker is not None:
            self._gemini_worker.cancel()
            self._gemini_worker.wait()
        diagnostic_worker = getattr(self, "_gemini_diagnostic_worker", None)
        if diagnostic_worker is not None:
            diagnostic_worker.wait()
        super().closeEvent(event)

    def _check_gemini_connection(self) -> None:
        """Explicit live diagnostic: lists accessible models without translating."""
        from gui.workers.gemini_worker import GeminiDiagnosticWorker

        self.gemini_check_button.setEnabled(False)
        self.gemini_status_label.setText(tr("Checking Gemini model access..."))
        self.gemini_status_label.show()
        worker = GeminiDiagnosticWorker(
            self._api_key, self, model_preference=self._model_preference
        )
        worker.finished.connect(self._on_gemini_diagnostic_finished)
        worker.error.connect(self._on_gemini_diagnostic_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._gemini_diagnostic_worker = worker
        worker.start()

    def _on_gemini_diagnostic_finished(self, result: object) -> None:
        self.gemini_check_button.setEnabled(bool(self._api_key))
        self.gemini_status_label.hide()
        self._gemini_diagnostic_worker = None
        selected = getattr(result, "selected_models", ())
        available = getattr(result, "available_models", ())
        if selected:
            QMessageBox.information(
                self,
                tr("Gemini Model Access"),
                tr("Model access succeeded. Selected model: {model}\nAvailable text models: {count}").format(
                    model=selected[0], count=len(available)
                ),
            )

    def _on_gemini_diagnostic_error(self, message: str) -> None:
        self.gemini_check_button.setEnabled(bool(self._api_key))
        self.gemini_status_label.hide()
        self._gemini_diagnostic_worker = None
        QMessageBox.warning(self, tr("Gemini Model Access"), message)

    def _on_gemini_finished(self, result: object) -> None:
        self.gemini_button.setEnabled(True)
        self.gemini_status_label.hide()
        self.cancel_gemini_button.hide()
        self.cancel_gemini_button.setEnabled(True)
        self._gemini_worker = None
        self._gemini_diagnostic_worker = None

        # Keep compatibility with callers that still emit the former dict
        # payload while presenting richer partial-success information to users.
        if isinstance(result, GeminiTranslationResult):
            results = result.translations
            if result.failures or result.cancelled:
                notes: list[str] = []
                if result.cancelled:
                    notes.append(tr("Cancelled; completed translations are still available."))
                if result.failures:
                    notes.append(
                        tr("{count} batch(es) failed: {reason}").format(
                            count=len(result.failures), reason=str(result.failures[0].error)
                        )
                    )
                QMessageBox.warning(self, tr("Gemini Partial Results"), "\n".join(notes))
        else:
            results = result if isinstance(result, dict) else {}

        if not results:
            QMessageBox.information(
                self,
                tr("No Results"),
                tr("Gemini returned no translations."),
            )
            return

        result_dialog = GeminiResultDialog(results, self._gemini_pending, self)
        if result_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        translations = result_dialog.get_translations()
        self._apply_gemini_translations(translations)

    def _on_gemini_error(self, message: str) -> None:
        self.gemini_button.setEnabled(True)
        self.gemini_status_label.hide()
        self.cancel_gemini_button.hide()
        self.cancel_gemini_button.setEnabled(True)
        self._gemini_worker = None
        QMessageBox.warning(self, tr("Gemini Error"), message)

    def _apply_gemini_translations(
        self, translations: dict[tuple[str, str], str]
    ) -> None:
        """Fill column 3 (Korean) in the main table from Gemini translations."""
        if not translations:
            return

        self._updating_table = True
        self.table.blockSignals(True)
        try:
            for row_idx in range(self.table.rowCount()):
                name_item = self.table.item(row_idx, 2)
                if name_item is None:
                    continue
                pending = name_item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(pending, PendingName):
                    continue
                korean = translations.get((pending.part, pending.name), "")
                if not korean:
                    continue
                korean_item = self.table.item(row_idx, 3)
                if korean_item is None:
                    korean_item = QTableWidgetItem()
                    self.table.setItem(row_idx, 3, korean_item)
                korean_item.setText(korean)
                korean_item.setData(SUGGESTION_ROLE, None)
                self._style_korean_cell(korean_item, is_recommendation=False)
        finally:
            self.table.blockSignals(False)
            self._updating_table = False

        applied = len(translations)
        QMessageBox.information(
            self,
            tr("Applied"),
            tr("{count:,} Gemini translation(s) applied to the table.\nClick 'Save Entered Items' to save.").format(
                count=applied
            ),
        )

    def _save_entries(self) -> None:
        self._store = KoreanNameStore.load()
        saved = 0
        errors: list[str] = []
        for row_idx in range(self.table.rowCount()):
            base_item = self.table.item(row_idx, 2)
            korean_item = self.table.item(row_idx, 3)
            if base_item is None or korean_item is None:
                continue
            pending = base_item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(pending, PendingName):
                continue
            korean = korean_item.text().strip()
            if not korean:
                continue
            try:
                self._store.apply_mapping(pending.part, pending.name, korean)
                saved += 1
            except ValueError as exc:
                errors.append(str(exc))
            except OSError as exc:
                errors.append(str(exc) or tr("Failed to save Korean name mapping file."))
                break

        if errors:
            QMessageBox.warning(self, tr("Save Error"), "\n".join(errors[:5]))
        if saved:
            QMessageBox.information(
                self,
                tr("Saved"),
                tr("{count:,} Korean name(s) saved.").format(count=saved),
            )
            self._reload_table()
        elif not errors:
            QMessageBox.information(self, tr("No Changes"), tr("No Korean names to save."))
