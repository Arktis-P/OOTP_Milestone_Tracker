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


class KoreanNameMappingDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Korean Name Mapping"))
        self.resize(*scale_size(1440, 1300))
        self._store = KoreanNameStore.load()
        self._updating_table = False

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
