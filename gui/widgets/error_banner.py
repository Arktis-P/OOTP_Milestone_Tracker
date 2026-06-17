"""Inline error/warning/info banner for tab views."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from gui.theme import AMBER_300, AMBER_800, AMBER_950, BLUE_300, BLUE_800, BLUE_950, RED_200, RED_400, RED_800, RED_950

_BANNER_STYLES = {
    "error": (
        f"background:{RED_950};color:{RED_200};"
        f"border:1px solid {RED_800};border-radius:8px;"
    ),
    "warning": (
        f"background:{AMBER_950};color:{AMBER_300};"
        f"border:1px solid {AMBER_800};border-radius:8px;"
    ),
    "info": (
        f"background:{BLUE_950};color:{BLUE_300};"
        f"border:1px solid {BLUE_800};border-radius:8px;"
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
        self._close.setStyleSheet(f"color: {RED_400}; font-weight: bold; border: none;")
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
