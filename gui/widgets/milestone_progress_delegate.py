"""Delegate that paints an inline progress bar for milestone prediction cells."""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.theme import ACCENT, BG_ELEVATED, RED_TEXT, TEXT_PRIMARY

# Cell data roles consumed by this delegate (set alongside the item's display text).
PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1
IS_NEAR_ROLE = Qt.ItemDataRole.UserRole + 2

_BAR_HEIGHT = 14
_BAR_MARGIN = 6
_RADIUS = 6.0


class MilestoneProgressDelegate(QStyledItemDelegate):
    """Paints a horizontal progress-style bar behind a cell's text.

    Cells opt in by carrying a 0-100 float on ``PROGRESS_ROLE``; ``IS_NEAR_ROLE``
    (bool) switches the fill color to the "near" red accent. Cells without
    ``PROGRESS_ROLE`` fall back to normal item painting.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        progress = index.data(PROGRESS_ROLE)
        if progress is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        progress = max(0.0, min(100.0, float(progress)))
        is_near = bool(index.data(IS_NEAR_ROLE))
        label = str(index.data(Qt.ItemDataRole.DisplayRole) or "")

        rect = option.rect
        bar_rect = QRectF(
            rect.x() + _BAR_MARGIN,
            rect.y() + (rect.height() - _BAR_HEIGHT) / 2,
            rect.width() - 2 * _BAR_MARGIN,
            _BAR_HEIGHT,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BG_ELEVATED))
        painter.drawRoundedRect(bar_rect, _RADIUS, _RADIUS)

        fill_width = bar_rect.width() * (progress / 100.0)
        if fill_width > 0:
            fill_rect = QRectF(bar_rect.x(), bar_rect.y(), fill_width, bar_rect.height())
            painter.setBrush(QColor(RED_TEXT if is_near else ACCENT))
            painter.drawRoundedRect(fill_rect, _RADIUS, _RADIUS)

        painter.setPen(QColor(TEXT_PRIMARY))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), _BAR_HEIGHT + 14))
        return size
