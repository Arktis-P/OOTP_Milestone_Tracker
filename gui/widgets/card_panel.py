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
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

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
        self.content_layout.setSpacing(10)
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


def tool_row(
    title: str,
    description: str,
    button: QWidget,
    *,
    badge: QLabel | None = None,
) -> QWidget:
    """Settings-style row: title + description on the left, action on the right."""
    row = QFrame()
    row.setObjectName("toolRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(12)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("toolRowTitle")
    desc_label = QLabel(description)
    desc_label.setObjectName("mutedLabel")
    desc_label.setWordWrap(True)
    text_col.addWidget(title_label)
    text_col.addWidget(desc_label)
    layout.addLayout(text_col, stretch=1)

    if badge is not None:
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

    layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
    return row
