"""Shared dialog chrome for the dark theme."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from gui.widgets.card_panel import CardPanel


def init_dialog_layout(dialog: QDialog) -> QVBoxLayout:
    """Standard outer margins and spacing for modal dialogs."""
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    return layout


def muted_label(text: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName("mutedLabel")
    if wrap:
        label.setWordWrap(True)
    return label


def summary_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("accentLabel")
    return label


def error_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("errorLabel")
    return label


def add_dialog_footer(layout: QVBoxLayout, widget: QWidget) -> None:
    layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignRight)


def style_primary_button(button: QPushButton) -> QPushButton:
    button.setObjectName("primaryButton")
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def make_button_box(
    *,
    save: bool = False,
    save_text: str = "Save",
    ok: bool = False,
    ok_text: str = "OK",
    close: bool = False,
    cancel: bool = True,
    custom_accept: tuple[str, QDialogButtonBox.ButtonRole] | None = None,
) -> QDialogButtonBox:
    box = QDialogButtonBox()
    if cancel:
        box.addButton(QDialogButtonBox.StandardButton.Cancel)
    if save:
        btn = box.addButton(tr(save_text), QDialogButtonBox.ButtonRole.AcceptRole)
        style_primary_button(btn)
    elif ok:
        btn = box.addButton(tr(ok_text), QDialogButtonBox.ButtonRole.AcceptRole)
        style_primary_button(btn)
    elif close:
        box.addButton(QDialogButtonBox.StandardButton.Close)
    if custom_accept is not None:
        label, role = custom_accept
        btn = box.addButton(tr(label), role)
        style_primary_button(btn)
    return box


def table_card(title: str | None, table: QWidget, *, trailing: QWidget | None = None) -> CardPanel:
    """Wrap a table widget in a card panel."""
    panel = CardPanel(title, trailing=trailing)
    panel.add_widget(table)
    return panel


def toolbar_row(*widgets: QWidget, stretch_index: int | None = None) -> QWidget:
    """Horizontal action row (e.g. load / browse buttons)."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for index, widget in enumerate(widgets):
        if stretch_index == index:
            layout.addWidget(widget, stretch=1)
        else:
            layout.addWidget(widget)
    layout.addStretch()
    return row
