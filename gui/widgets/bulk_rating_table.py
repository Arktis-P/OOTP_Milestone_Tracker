"""Virtualized table model + delegates for bulk rating edit."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from core.roster.bulk_rating import FameLevel, PlayerBulkSettings

_FAME_OPTIONS: list[tuple[str, FameLevel]] = [
    ("미선택", FameLevel.NONE),
    ("지역구", FameLevel.REGIONAL),
    ("전국구", FameLevel.NATIONAL),
    ("슈퍼스타", FameLevel.SUPERSTAR),
]

_FAME_LABEL_BY_LEVEL = {level: label for label, level in _FAME_OPTIONS}
_FAME_LEVEL_BY_LABEL = {label: level for label, level in _FAME_OPTIONS}

COL_EN = 0
COL_KO = 1
COL_AGE = 2
COL_PROSPECT = 3
COL_BASE = 4
COL_PROSPECT_FAME = 5

HEADERS = ["영문명", "한글명", "나이", "유망주", "기본 인지도", "유망주 인지도"]


@dataclass(frozen=True)
class BulkPlayerIndex:
    player_id: int
    display_name: str
    name_lower: str
    nation: str
    position: str
    source: str


class BulkRatingTableModel(QAbstractTableModel):
    prospect_manual_changed = pyqtSignal(int)

    def __init__(
        self,
        indices: list[BulkPlayerIndex],
        settings: dict[int, PlayerBulkSettings],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._indices = indices
        self._settings = settings
        self._visible: list[int] = list(range(len(indices)))
        self._prospect_manual: set[int] = set()

    def set_visible_rows(self, visible_positions: list[int]) -> None:
        self.beginResetModel()
        self._visible = visible_positions
        self.endResetModel()

    def player_id_at(self, row: int) -> int | None:
        if row < 0 or row >= len(self._visible):
            return None
        pos = self._visible[row]
        if pos < 0 or pos >= len(self._indices):
            return None
        return self._indices[pos].player_id

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        col = index.column()
        if col in (COL_AGE, COL_PROSPECT, COL_BASE, COL_PROSPECT_FAME):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        meta = self._meta_at(index.row())
        if meta is None:
            return None
        cfg = self._settings[meta.player_id]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_EN:
                return meta.display_name
            if col == COL_KO:
                return ""
            if col == COL_AGE:
                return str(cfg.age)
            if col == COL_PROSPECT:
                return ""
            if col == COL_BASE:
                return _FAME_LABEL_BY_LEVEL[cfg.base_fame]
            if col == COL_PROSPECT_FAME:
                return _FAME_LABEL_BY_LEVEL[cfg.prospect_fame]

        if role == Qt.ItemDataRole.CheckStateRole and col == COL_PROSPECT:
            return (
                Qt.CheckState.Checked
                if cfg.is_prospect
                else Qt.CheckState.Unchecked
            )

        if role == Qt.ItemDataRole.TextAlignmentRole and col in (
            COL_AGE,
            COL_PROSPECT,
            COL_BASE,
            COL_PROSPECT_FAME,
        ):
            return int(Qt.AlignmentFlag.AlignCenter)

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
        meta = self._meta_at(index.row())
        if meta is None:
            return False
        cfg = self._settings[meta.player_id]
        col = index.column()

        if col == COL_AGE and role == Qt.ItemDataRole.EditRole:
            try:
                cfg.age = max(0, int(str(value).strip()))
            except ValueError:
                return False
            if meta.player_id not in self._prospect_manual:
                cfg.is_prospect = cfg.age <= 25
                prospect_index = self.index(index.row(), COL_PROSPECT)
                self.dataChanged.emit(prospect_index, prospect_index)
            self.dataChanged.emit(index, index)
            return True

        if col == COL_PROSPECT and role == Qt.ItemDataRole.CheckStateRole:
            self._prospect_manual.add(meta.player_id)
            cfg.prospect_manual = True
            checked = value == Qt.CheckState.Checked or value == int(Qt.CheckState.Checked)
            cfg.is_prospect = checked
            self.prospect_manual_changed.emit(meta.player_id)
            self.dataChanged.emit(index, index)
            return True

        if col in (COL_BASE, COL_PROSPECT_FAME) and role == Qt.ItemDataRole.EditRole:
            level = _FAME_LEVEL_BY_LABEL.get(str(value), FameLevel.NONE)
            if col == COL_BASE:
                cfg.base_fame = level
            else:
                cfg.prospect_fame = level
            self.dataChanged.emit(index, index)
            return True

        return False

    def _meta_at(self, row: int) -> BulkPlayerIndex | None:
        if row < 0 or row >= len(self._visible):
            return None
        pos = self._visible[row]
        if pos < 0 or pos >= len(self._indices):
            return None
        return self._indices[pos]


class FameComboDelegate(QStyledItemDelegate):
    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QWidget:
        combo = QComboBox(parent)
        for label, _level in _FAME_OPTIONS:
            combo.addItem(label)
        return combo

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if isinstance(editor, QComboBox):
            text = str(index.model().data(index, Qt.ItemDataRole.DisplayRole) or "")
            row = editor.findText(text)
            if row >= 0:
                editor.setCurrentIndex(row)

    def setModelData(
        self, editor: QWidget, model: QAbstractTableModel, index: QModelIndex
    ) -> None:
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)
