"""Shared table and filter bar widgets."""

from __future__ import annotations

from typing import Any, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


class FilterBar(QWidget):
    """Search/filter input bar placed above tables."""

    def __init__(self, placeholder: str = tr("Search..."), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search_input)

    @property
    def text(self) -> str:
        return self.search_input.text()

    def clear(self) -> None:
        self.search_input.clear()


class NumericSortItem(QTableWidgetItem):
    """Table cell that sorts by numeric value instead of display text."""

    def __init__(self, display: str, sort_value: float | int) -> None:
        super().__init__(display)
        self._sort_value = float(sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericSortItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


class SortableTable(QTableWidget):
    """QTableWidget with sortable headers and helper methods."""

    def __init__(self, columns: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(list(columns))
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def populate(self, rows: Sequence[Sequence[Any]]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row_idx, col_idx, item)
        self.setSortingEnabled(True)

    def filter_rows(self, text: str, columns: Sequence[int] | None = None) -> None:
        needle = text.strip().lower()
        search_columns = list(columns) if columns is not None else range(self.columnCount())
        for row in range(self.rowCount()):
            if not needle:
                self.setRowHidden(row, False)
                continue
            visible = False
            for col in search_columns:
                item = self.item(row, col)
                if item and needle in item.text().lower():
                    visible = True
                    break
            self.setRowHidden(row, not visible)


class TablePanel(QWidget):
    """Filter bar + sortable table combo."""

    def __init__(self, columns: Sequence[str], placeholder: str = tr("Search..."), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.filter_bar = FilterBar(placeholder)
        self.table = SortableTable(columns)
        self.filter_bar.search_input.textChanged.connect(self._on_filter_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_bar)
        layout.addWidget(self.table)

    def _on_filter_changed(self, text: str) -> None:
        self.table.filter_rows(text)
