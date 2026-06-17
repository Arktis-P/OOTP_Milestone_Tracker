"""Inline error/warning/info banner for tab views."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

_BANNER_STYLES = {
    "error": "background:#FEE2E2;color:#991B1B;border:1px solid #FCA5A5;",
    "warning": "background:#FEF3C7;color:#92400E;border:1px solid #FCD34D;",
    "info": "background:#DBEAFE;color:#1E40AF;border:1px solid #93C5FD;",
}


class ErrorBanner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._close = QPushButton("×")
        self._close.setFixedWidth(28)
        self._close.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
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
