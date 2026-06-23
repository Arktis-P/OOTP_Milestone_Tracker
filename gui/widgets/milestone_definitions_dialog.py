"""Manage milestone definitions (milestones.csv)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.milestone.definitions import (
    MilestoneDefinition,
    MilestoneDefinitions,
    load_milestones,
    save_milestones_csv,
)
from gui.widgets.milestone_definition_form_dialog import MilestoneDefinitionFormDialog
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import (
    add_dialog_footer,
    init_dialog_layout,
    make_button_box,
    muted_label,
    summary_label,
    table_card,
    toolbar_row,
)
from gui.widgets.table_widgets import FilterBar


class MilestoneDefinitionsDialog(QDialog):
    definitions_changed = pyqtSignal()

    def __init__(self, milestones_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.milestones_path = milestones_path
        self._definitions = load_milestones(milestones_path)
        self._items: list[MilestoneDefinition] = list(self._definitions.all_milestones)

        self.setWindowTitle(tr("Milestone Definition Management"))
        self.resize(*scale_size(1960, 1400))

        intro = muted_label(
            tr("Milestone definitions used for achievement detection.\nFile: {path}").format(
                path=milestones_path
            )
        )

        self.summary_label = summary_label()
        self.filter_bar = FilterBar(tr("Search by key, name, scope..."))
        self.filter_bar.search_input.textChanged.connect(self._reload_table)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["key", tr("Display Name"), tr("Category"), "scope", "stat", "threshold", "grade", tr("Active")]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._edit_selected())

        self.add_button = QPushButton(tr("Add"))
        self.edit_button = QPushButton(tr("Edit"))
        self.delete_button = QPushButton(tr("Delete"))
        self.add_button.clicked.connect(self._add_item)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)

        button_row = toolbar_row(
            self.add_button,
            self.edit_button,
            self.delete_button,
        )
        hint = muted_label(tr("Double-click to edit"), wrap=False)

        close_buttons = make_button_box(close=True, cancel=False)
        close_buttons.rejected.connect(self.reject)

        table_panel = table_card(tr("Definitions List"), self.table)

        layout = init_dialog_layout(self)
        layout.addWidget(intro)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.filter_bar)
        layout.addWidget(table_panel, stretch=1)
        layout.addWidget(button_row)
        layout.addWidget(hint)
        add_dialog_footer(layout, close_buttons)

        self._reload_table()

    def _reload_table(self) -> None:
        needle = self.filter_bar.text.strip().casefold()
        rows = self._items
        if needle:
            rows = [
                item
                for item in self._items
                if needle in item.key.casefold()
                or needle in item.label.casefold()
                or needle in item.scope.casefold()
            ]

        active_count = sum(1 for item in self._items if item.active)
        summary = tr("Total {total} · Active {active}").format(
            total=len(self._items), active=active_count
        )
        if needle:
            summary += tr(" · Showing {shown}").format(shown=len(rows))
        self.summary_label.setText(summary)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            values = [
                item.key,
                item.label,
                item.category,
                item.scope,
                item.stat,
                item.threshold,
                item.grade,
                "Y" if item.active else "",
            ]
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem("" if value is None else str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cell.setData(Qt.ItemDataRole.UserRole, item.key)
                self.table.setItem(row_idx, col_idx, cell)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def _selected_key(self) -> str | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        if item is None:
            return None
        key = item.data(Qt.ItemDataRole.UserRole)
        return str(key) if key else None

    def _find_index(self, key: str) -> int | None:
        for index, item in enumerate(self._items):
            if item.key == key:
                return index
        return None

    def _existing_keys(self) -> set[str]:
        return {item.key for item in self._items}

    def _persist(self) -> bool:
        definitions = MilestoneDefinitions(
            batting=[item for item in self._items if item.category == "batting"],
            pitching=[item for item in self._items if item.category == "pitching"],
            team=[item for item in self._items if item.category == "team"],
        )
        try:
            save_milestones_csv(self.milestones_path, definitions)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, tr("Save Failed"), str(exc))
            return False
        self._definitions = definitions
        self.definitions_changed.emit()
        return True

    def _add_item(self) -> None:
        dialog = MilestoneDefinitionFormDialog(
            existing_keys=self._existing_keys(),
            parent=self,
        )
        if not dialog.exec():
            return
        item = dialog.result_item()
        if item is None:
            return
        self._items.append(item)
        if self._persist():
            self._reload_table()

    def _edit_selected(self) -> None:
        key = self._selected_key()
        if not key:
            QMessageBox.information(self, tr("Edit"), tr("Please select a definition to edit."))
            return
        index = self._find_index(key)
        if index is None:
            return
        dialog = MilestoneDefinitionFormDialog(
            existing_keys=self._existing_keys(),
            item=self._items[index],
            parent=self,
        )
        if not dialog.exec():
            return
        item = dialog.result_item()
        if item is None:
            return
        self._items[index] = item
        if self._persist():
            self._reload_table()

    def _delete_selected(self) -> None:
        key = self._selected_key()
        if not key:
            QMessageBox.information(self, tr("Delete"), tr("Please select a definition to delete."))
            return
        index = self._find_index(key)
        if index is None:
            return
        item = self._items[index]
        confirm = QMessageBox.question(
            self,
            tr("Delete Milestone Definition"),
            tr("'{label}' ({key}) definition will be deleted.\n\nRecorded milestone history will not be deleted.").format(
                label=item.label, key=item.key
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        del self._items[index]
        if self._persist():
            self._reload_table()
