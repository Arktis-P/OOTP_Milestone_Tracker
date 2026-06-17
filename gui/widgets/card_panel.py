"""Rounded card panels (prototype-style sections)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class CardPanel(QFrame):
    """Bordered panel with optional title header and trailing action."""

    def __init__(
        self,
        title: str | None = None,
        *,
        trailing: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cardPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        if title or trailing is not None:
            header = QHBoxLayout()
            header.setSpacing(8)
            if title:
                title_label = QLabel(title)
                title_label.setObjectName("cardTitle")
                header.addWidget(title_label)
            header.addStretch()
            if trailing is not None:
                header.addWidget(trailing)
            root.addLayout(header)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        root.addLayout(self.content_layout)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.content_layout.addLayout(layout)

    def add_stretch(self) -> None:
        self.content_layout.addStretch()


def section_label(text: str) -> QLabel:
    """Uppercase muted label for filter groups."""
    label = QLabel(text)
    label.setObjectName("sectionLabel")
    return label
