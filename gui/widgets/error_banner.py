"""Inline error/warning/info banner for tab views."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from gui.theme import AMBER_BG, AMBER_BORDER, AMBER_TEXT, BLUE_BG, BLUE_BORDER, BLUE_TEXT, RED_BG, RED_BORDER, RED_TEXT

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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self._label, stretch=1)
        layout.addWidget(self._close)

    def show_error(self, message: str) -> None:
        self._show(message, "error")

    def show_warning(self, message: str) -> None:
        self._show(message, "warning")

    def show_info(self, message: str) -> None:
        self._show(message, "info")

    def _show(self, message: str, kind: str) -> None:
        self._label.setText(message)
        self.setStyleSheet(_BANNER_STYLES[kind])
        self.setVisible(True)
