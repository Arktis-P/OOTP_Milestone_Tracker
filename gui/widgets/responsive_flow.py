"""Reusable responsive layout helpers for PyQt screens."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLayout,
    QLayoutItem,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


class ResponsiveFlowLayout(QLayout):
    """Flow layout that wraps child widgets when horizontal space is limited.

    Qt's box layouts keep controls on one horizontal line unless each caller
    manually restructures the UI. This layout keeps the API close to
    ``QHBoxLayout`` for filters/buttons, but computes height-for-width and
    places items on additional rows when the available width is too small.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = 0,
        horizontal_spacing: int = 8,
        vertical_spacing: int = 8,
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._horizontal_spacing = horizontal_spacing
        self._vertical_spacing = vertical_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self) -> None:
        while self.takeAt(0) is not None:
            pass

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt API
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 - Qt API
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt API
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt API
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())

        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def horizontalSpacing(self) -> int:  # noqa: N802 - Qt API
        return self._smart_spacing(
            QStyle.PixelMetric.PM_LayoutHorizontalSpacing,
            self._horizontal_spacing,
        )

    def verticalSpacing(self) -> int:  # noqa: N802 - Qt API
        return self._smart_spacing(
            QStyle.PixelMetric.PM_LayoutVerticalSpacing,
            self._vertical_spacing,
        )

    def _smart_spacing(self, metric: QStyle.PixelMetric, fallback: int) -> int:
        parent = self.parent()
        if parent is None or not isinstance(parent, QWidget):
            return fallback
        spacing = parent.style().pixelMetric(metric, None, parent)
        return fallback if spacing < 0 else spacing

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)

        x = effective.x()
        y = effective.y()
        line_height = 0
        horizontal_spacing = self.horizontalSpacing()
        vertical_spacing = self.verticalSpacing()

        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue

            hint = item.sizeHint()
            next_x = x + hint.width() + horizontal_spacing
            if line_height > 0 and next_x - horizontal_spacing > effective.right() + 1:
                x = effective.x()
                y += line_height + vertical_spacing
                next_x = x + hint.width() + horizontal_spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


class CollapsibleSection(QFrame):
    """Section wrapper that can hide lower-priority controls on narrow screens."""

    def __init__(
        self,
        title: str,
        content: QWidget | None = None,
        *,
        expanded: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self.toggle_button = QToolButton(self)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setText(title)
        self.toggle_button.setAccessibleName(title)
        self.toggle_button.setAccessibleDescription(
            tr("Expand or collapse this section.")
        )

        self.content_widget = content or QWidget(self)
        self.content_widget.setVisible(expanded)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(self.toggle_button)
        root.addWidget(self.content_widget)

        self.toggle_button.toggled.connect(self.set_expanded)

    def is_expanded(self) -> bool:
        return self.toggle_button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.content_widget.setVisible(expanded)
        self.updateGeometry()

