"""Virtualized table model + painted fame radio delegate for bulk rating edit."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionButton, QStyleOptionViewItem, QStyledItemDelegate, QWidget

from core.i18n import tr
from core.roster.bulk_rating import FameLevel, PlayerBulkSettings

_FAME_OPTIONS: list[tuple[str, FameLevel]] = [
    (tr("None"), FameLevel.NONE),
    (tr("Regional"), FameLevel.REGIONAL),
    (tr("National"), FameLevel.NATIONAL),
    (tr("Superstar"), FameLevel.SUPERSTAR),
]

_FAME_SHORT_LABELS = ("—", tr("Reg"), tr("Nat"), tr("Super"))
_FAME_LEVELS = tuple(level for _label, level in _FAME_OPTIONS)
_FAME_LABEL_BY_LEVEL = {level: label for label, level in _FAME_OPTIONS}

COL_EN = 0
COL_KO = 1
COL_TEAM = 2
COL_AGE = 3
COL_PROSPECT = 4
COL_BASE = 5
COL_PROSPECT_FAME = 6

HEADERS = [tr("English Name"), tr("Korean Name"), tr("Team"), tr("Age"), tr("Prospect"), tr("Base Fame"), tr("Prospect Fame")]
FAME_COLUMNS = (COL_BASE, COL_PROSPECT_FAME)


_FAME_SORT_RANK = {level: index for index, level in enumerate(_FAME_LEVELS)}


@dataclass(frozen=True)
class BulkPlayerIndex:
    player_id: int
    display_name: str
    name_lower: str
    korean_name: str
    korean_name_lower: str
    team: str
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

    def sort(
        self,
        column: int,
        order: Qt.SortOrder = Qt.SortOrder.AscendingOrder,
    ) -> None:
        reverse = order == Qt.SortOrder.DescendingOrder

        def sort_key(visible_pos: int):
            meta = self._indices[visible_pos]
            cfg = self._settings[meta.player_id]
            if column == COL_EN:
                return meta.name_lower
            if column == COL_KO:
                return meta.korean_name_lower
            if column == COL_TEAM:
                return meta.team.casefold()
            if column == COL_AGE:
                return cfg.age
            if column == COL_PROSPECT:
                return int(cfg.is_prospect)
            if column == COL_BASE:
                return _FAME_SORT_RANK.get(cfg.base_fame, 0)
            if column == COL_PROSPECT_FAME:
                return _FAME_SORT_RANK.get(cfg.prospect_fame, 0)
            return ""

        self.layoutAboutToBeChanged.emit()
        self._visible.sort(key=sort_key, reverse=reverse)
        self.layoutChanged.emit()

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
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            if section in FAME_COLUMNS:
                return tr("Click to select · Click again to deselect")
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        col = index.column()
        if col == COL_PROSPECT:
            return base | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable
        if col == COL_AGE:
            return base | Qt.ItemFlag.ItemIsEditable
        if col in FAME_COLUMNS:
            return base
        return base

    def _fame_level(self, meta: BulkPlayerIndex, col: int) -> FameLevel:
        cfg = self._settings[meta.player_id]
        if col == COL_BASE:
            return cfg.base_fame
        return cfg.prospect_fame

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
                return meta.korean_name
            if col == COL_TEAM:
                return meta.team
            if col == COL_AGE:
                return str(cfg.age)
            if col == COL_PROSPECT:
                return ""
            if col in FAME_COLUMNS:
                return ""

        if role == Qt.ItemDataRole.UserRole and col in FAME_COLUMNS:
            return self._fame_level(meta, col)

        if role == Qt.ItemDataRole.CheckStateRole and col == COL_PROSPECT:
            return (
                Qt.CheckState.Checked
                if cfg.is_prospect
                else Qt.CheckState.Unchecked
            )

        if role == Qt.ItemDataRole.TextAlignmentRole and col in (
            COL_AGE,
            COL_PROSPECT,
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

        if col in FAME_COLUMNS and role == Qt.ItemDataRole.EditRole:
            level = value if isinstance(value, FameLevel) else FameLevel.NONE
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


def _segment_rects(cell_rect: QRect, count: int) -> list[QRect]:
    if count <= 0 or cell_rect.width() <= 0:
        return []
    seg_width = cell_rect.width() // count
    rects: list[QRect] = []
    for i in range(count):
        left = cell_rect.left() + i * seg_width
        width = seg_width if i < count - 1 else cell_rect.right() - left + 1
        rects.append(QRect(left, cell_rect.top(), width, cell_rect.height()))
    return rects


def _segment_index_at(cell_rect: QRect, pos) -> int | None:
    for index, rect in enumerate(_segment_rects(cell_rect, len(_FAME_LEVELS))):
        if rect.contains(pos):
            return index
    return None


class FameRadioDelegate(QStyledItemDelegate):
    """Paint four inline radio choices per fame cell; click toggles or clears selection."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() not in FAME_COLUMNS:
            super().paint(painter, option, index)
            return

        self.initStyleOption(option, index)
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        current = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(current, FameLevel):
            current = FameLevel.NONE

        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is None:
            painter.restore()
            return

        fm = painter.fontMetrics()
        indicator_size = style.pixelMetric(
            QStyle.PixelMetric.PM_IndicatorWidth, None, widget
        )
        spacing = style.pixelMetric(
            QStyle.PixelMetric.PM_RadioButtonLabelSpacing, None, widget
        )

        for seg_index, (level, short_label) in enumerate(
            zip(_FAME_LEVELS, _FAME_SHORT_LABELS, strict=True)
        ):
            seg_rect = _segment_rects(option.rect, len(_FAME_LEVELS))[seg_index]
            if seg_rect.isEmpty():
                continue

            indicator_opt = QStyleOptionButton()
            indicator_opt.initFrom(widget)
            indicator_opt.state = QStyle.StateFlag.State_Enabled
            if level == current:
                indicator_opt.state |= QStyle.StateFlag.State_On
            else:
                indicator_opt.state |= QStyle.StateFlag.State_Off

            text_width = fm.horizontalAdvance(short_label)
            content_width = indicator_size + spacing + text_width
            content_left = seg_rect.left() + max(0, (seg_rect.width() - content_width) // 2)
            content_top = seg_rect.top() + (seg_rect.height() - indicator_size) // 2

            indicator_opt.rect = QRect(
                content_left,
                content_top,
                indicator_size,
                indicator_size,
            )
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorRadioButton,
                indicator_opt,
                painter,
                widget,
            )

            text_rect = QRect(
                content_left + indicator_size + spacing,
                seg_rect.top(),
                text_width,
                seg_rect.height(),
            )
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                short_label,
            )

        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractTableModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        if index.column() not in FAME_COLUMNS:
            return super().editorEvent(event, model, option, index)

        if event.type() not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        ):
            return False

        mouse_event = event
        if not isinstance(mouse_event, QMouseEvent):
            return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            return True
        if mouse_event.button() != Qt.MouseButton.LeftButton:
            return False

        seg_index = _segment_index_at(option.rect, mouse_event.position().toPoint())
        if seg_index is None:
            return False

        picked = _FAME_LEVELS[seg_index]
        current = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(current, FameLevel):
            current = FameLevel.NONE
        new_level = FameLevel.NONE if picked == current else picked
        return model.setData(index, new_level, Qt.ItemDataRole.EditRole)

    def helpEvent(self, event, view, option, index):
        if index.column() in FAME_COLUMNS:
            level = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(level, FameLevel):
                from PyQt6.QtWidgets import QToolTip

                full = _FAME_LABEL_BY_LEVEL.get(level, tr("None"))
                QToolTip.showText(event.globalPos(), full, view)
                return True
        return super().helpEvent(event, view, option, index)
