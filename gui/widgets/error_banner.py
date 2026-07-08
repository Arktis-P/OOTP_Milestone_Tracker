"""Inline error/warning/info/success banner for tab views, with optional action buttons."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.theme import (
    AMBER_BG,
    AMBER_BORDER,
    AMBER_TEXT,
    BLUE_BG,
    BLUE_BORDER,
    BLUE_TEXT,
    GREEN_BG,
    GREEN_BORDER,
    GREEN_TEXT,
    RED_BG,
    RED_BORDER,
    RED_TEXT,
)

_BANNER_STYLES = {
    "error": (
        f"background:{RED_BG};color:{RED_TEXT};"
        f"border:1px solid {RED_BORDER};border-radius:8px;"
    ),
    "warning": (
        f"background:{AMBER_BG};color:{AMBER_TEXT};"
        f"border:1px solid {AMBER_BORDER};border-radius:8px;"
    ),
    "info": (
        f"background:{BLUE_BG};color:{BLUE_TEXT};"
        f"border:1px solid {BLUE_BORDER};border-radius:8px;"
    ),
    "success": (
        f"background:{GREEN_BG};color:{GREEN_TEXT};"
        f"border:1px solid {GREEN_BORDER};border-radius:8px;"
    ),
}


class ErrorBanner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._close = QPushButton("×")
        self._close.setFixedWidth(28)
        self._close.setFlat(True)
        self._close.setStyleSheet(f"color: {RED_TEXT}; font-weight: bold; border: none;")
        self._close.clicked.connect(self.hide)

        top_row = QHBoxLayout()
        top_row.addWidget(self._label, stretch=1)
        top_row.addWidget(self._close)

        self._actions_row = QHBoxLayout()
        self._actions_row.setSpacing(8)
        self._actions_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addLayout(top_row)
        layout.addLayout(self._actions_row)

    def show_error(
        self, message: str, actions: list[tuple[str, Callable[[], None]]] | None = None
    ) -> None:
        self._show(message, "error", actions)

    def show_warning(
        self, message: str, actions: list[tuple[str, Callable[[], None]]] | None = None
    ) -> None:
        self._show(message, "warning", actions)

    def show_info(
        self, message: str, actions: list[tuple[str, Callable[[], None]]] | None = None
    ) -> None:
        self._show(message, "info", actions)

    def show_success(
        self, message: str, actions: list[tuple[str, Callable[[], None]]] | None = None
    ) -> None:
        self._show(message, "success", actions)

    def _show(
        self,
        message: str,
        kind: str,
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        self._label.setText(message)
        self.setStyleSheet(_BANNER_STYLES[kind])
        self._set_actions(actions or [])
        self.setVisible(True)

    def _set_actions(self, actions: list[tuple[str, Callable[[], None]]]) -> None:
        while self._actions_row.count() > 1:
            item = self._actions_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, callback in actions:
            button = QPushButton(label)
            button.setObjectName("linkButton")
            button.clicked.connect(callback)
            self._actions_row.insertWidget(self._actions_row.count() - 1, button)
