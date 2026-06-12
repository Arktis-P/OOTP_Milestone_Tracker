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

from core.milestone.definitions import (
    MilestoneDefinition,
    MilestoneDefinitions,
    load_milestones,
    save_milestones_csv,
)
from gui.widgets.milestone_definition_form_dialog import MilestoneDefinitionFormDialog
from gui.widgets.table_widgets import FilterBar


class MilestoneDefinitionsDialog(QDialog):
    definitions_changed = pyqtSignal()

    def __init__(self, milestones_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.milestones_path = milestones_path
        self._definitions = load_milestones(milestones_path)
        self._items: list[MilestoneDefinition] = list(self._definitions.all_milestones)

        self.setWindowTitle("마일스톤 기준 관리")
        self.resize(980, 560)

        intro = QLabel(
            f"마일스톤 달성 판정에 사용되는 기준 목록입니다.\n"
            f"파일: {milestones_path}"
        )
        intro.setWordWrap(True)

        self.summary_label = QLabel()
        self.filter_bar = FilterBar("key·이름·scope 검색...")
        self.filter_bar.search_input.textChanged.connect(self._reload_table)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["key", "표시 이름", "분류", "scope", "stat", "threshold", "grade", "활성"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._edit_selected())

        self.add_button = QPushButton("추가")
        self.edit_button = QPushButton("수정")
        self.delete_button = QPushButton("삭제")
        self.add_button.clicked.connect(self._add_item)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.delete_button)
        button_row.addStretch()
        button_row.addWidget(QLabel("더블클릭: 수정"))

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.filter_bar)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(button_row)
        layout.addWidget(close_buttons)

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
        self.summary_label.setText(
            f"전체 {len(self._items)}건 · 활성 {active_count}건"
            + (f" · 표시 {len(rows)}건" if needle else "")
        )

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
            QMessageBox.critical(self, "저장 실패", str(exc))
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
            QMessageBox.information(self, "수정", "수정할 기준을 선택하세요.")
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
            QMessageBox.information(self, "삭제", "삭제할 기준을 선택하세요.")
            return
        index = self._find_index(key)
        if index is None:
            return
        item = self._items[index]
        confirm = QMessageBox.question(
            self,
            "마일스톤 기준 삭제",
            f"'{item.label}' ({item.key}) 기준을 삭제하시겠습니까?\n\n"
            "이미 기록된 마일스톤 이력은 삭제되지 않습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        del self._items[index]
        if self._persist():
            self._reload_table()
