"""Empty-state placeholder — explains why a list is empty and what to do next."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gui.theme import TEXT_SECONDARY, hint_style


class EmptyStateWidget(QWidget):
    """Icon + title + subtitle + optional action buttons, centered."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = QLabel()
        self._icon.setStyleSheet("font-size: 22px;")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setStyleSheet("font-weight: 600;")
        self._subtitle = QLabel()
        self._subtitle.setWordWrap(True)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._subtitle.setStyleSheet(hint_style(TEXT_SECONDARY))

        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(8)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.addStretch()
        layout.addWidget(self._icon)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addLayout(self._button_row)
        layout.addStretch()

    def set_content(
        self,
        icon: str,
        title: str,
        subtitle: str,
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        self._icon.setText(icon)
        self._title.setText(title)
        self._subtitle.setText(subtitle)

        while self._button_row.count():
            item = self._button_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._button_row.addStretch()
        for label, callback in actions or []:
            button = QPushButton(label)
            button.setObjectName("linkButton")
            button.clicked.connect(callback)
            self._button_row.insertWidget(self._button_row.count() - 1, button)
        self._button_row.addStretch()
