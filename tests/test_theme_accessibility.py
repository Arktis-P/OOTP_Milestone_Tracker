from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

from gui.theme import apply_app_theme, apply_high_contrast_overrides, choose_app_font_family


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_theme_exposes_text_roles_and_keyboard_focus() -> None:
    app = qapp()
    apply_app_theme(app)
    sheet = app.styleSheet()

    for object_name in (
        "sectionTitle",
        "playerName",
        "primaryStat",
        "secondaryStat",
        "fieldLabel",
        "helperText",
        "statusText",
        "warningText",
    ):
        assert f"QLabel#{object_name}" in sheet

    for selector in (
        "QPushButton:focus",
        "QLineEdit:focus",
        "QPlainTextEdit:focus",
        "QListWidget:focus",
        "QTableWidget:focus",
        "QTabBar:focus",
        "QCheckBox:focus",
    ):
        assert selector in sheet

    assert "QCheckBox::indicator:disabled" in sheet


def test_high_contrast_override_can_be_toggled() -> None:
    app = qapp()
    apply_app_theme(app)
    base_sheet = app.styleSheet()

    apply_high_contrast_overrides(app, True)
    assert app.styleSheet() != base_sheet
    assert "border: 3px solid #ffff00" in app.styleSheet()
    assert app.palette().color(QPalette.ColorRole.Window).name() == "#000000"

    apply_high_contrast_overrides(app, False)
    assert app.styleSheet() == base_sheet


def test_theme_chooses_an_available_ui_font_family() -> None:
    app = qapp()
    family = choose_app_font_family()
    installed = {item.casefold() for item in QFontDatabase.families()}
    system_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()

    assert family
    assert family.casefold() in installed or family == system_family
    assert family != "sans-serif"

    apply_app_theme(app)
    assert app.font().family()
    assert app.font().family() != "sans-serif"
