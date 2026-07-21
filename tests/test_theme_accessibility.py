from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from gui.theme import apply_app_theme, apply_high_contrast_overrides


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_theme_exposes_accessible_text_role_selectors() -> None:
    app = qapp()

    apply_app_theme(app)
    sheet = app.styleSheet()

    for object_name in (
        "playerName",
        "primaryStat",
        "secondaryStat",
        "fieldLabel",
        "helperText",
        "statusText",
        "warningText",
    ):
        assert f"QLabel#{object_name}" in sheet

    assert "min-height: 34px" in sheet
    assert "border-left: 4px solid" in sheet


def test_theme_keeps_visible_keyboard_focus_for_common_controls() -> None:
    app = qapp()

    apply_app_theme(app)
    sheet = app.styleSheet()

    for selector in (
        "QPushButton:focus",
        "QLineEdit:focus",
        "QSpinBox:focus",
        "QComboBox:focus",
        "QTextEdit:focus",
        "QPlainTextEdit:focus",
        "QListWidget:focus",
        "QTableWidget:focus",
        "QTableView:focus",
        "QTabBar:focus",
        "QCheckBox:focus",
        "QRadioButton:focus",
    ):
        assert selector in sheet

    assert "outline: 2px solid" in sheet
    assert "font-weight: 600" in sheet
    assert "QCheckBox::indicator:disabled" in sheet


def test_high_contrast_override_can_be_enabled_and_disabled() -> None:
    app = qapp()

    apply_app_theme(app)
    base_sheet = app.styleSheet()

    apply_high_contrast_overrides(app, True)
    high_contrast_sheet = app.styleSheet()

    assert high_contrast_sheet != base_sheet
    assert "outline: 3px solid #ffff00" in high_contrast_sheet
    assert "border-left: 6px solid #ffff00" in high_contrast_sheet
    assert app.palette().color(QPalette.ColorRole.Window).name() == "#000000"

    apply_high_contrast_overrides(app, False)

    assert app.styleSheet() == base_sheet


def test_theme_offscreen_smoke_with_common_widgets() -> None:
    app = qapp()
    apply_app_theme(app)

    root = QWidget()
    layout = QVBoxLayout(root)

    for object_name, text in (
        ("playerName", "Sample Player"),
        ("primaryStat", "714 HR"),
        ("secondaryStat", "12 remaining"),
        ("fieldLabel", "Season"),
        ("helperText", "Use filters to narrow the visible records."),
        ("statusText", "Ready"),
        ("warningText", "Warning: backup path should be checked."),
    ):
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        layout.addWidget(label)

    layout.addWidget(QPushButton("Apply"))
    layout.addWidget(QLineEdit("filter"))
    layout.addWidget(QComboBox())
    layout.addWidget(QListWidget())
    layout.addWidget(QTableWidget(1, 1))
    layout.addWidget(QTabWidget())
    layout.addWidget(QCheckBox("Only visible rows"))
    layout.addWidget(QRadioButton("Season"))

    root.resize(480, 640)
    root.show()
    app.processEvents()

    assert root.isVisible()

    apply_high_contrast_overrides(app, True)
    app.processEvents()
    assert "outline: 3px solid #ffff00" in app.styleSheet()

    root.close()
