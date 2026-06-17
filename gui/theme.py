"""Conventional dark-mode theme for PyQt6 (VS Code / Windows style)."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

# Base surfaces
BG_WINDOW = "#1e1e1e"
BG_SIDEBAR = "#181818"
BG_PANEL = "#252526"
BG_ELEVATED = "#2d2d2d"
BG_INPUT = "#3c3c3c"
BG_HOVER = "#2a2d2e"

# Borders & text
BORDER = "#3e3e42"
BORDER_SUBTLE = "#333333"
TEXT_PRIMARY = "#cccccc"
TEXT_SECONDARY = "#9d9d9d"
TEXT_MUTED = "#6e6e6e"

# Accent (standard blue)
ACCENT = "#0078d4"
ACCENT_HOVER = "#1a86d9"
ACCENT_PRESSED = "#006cbe"
ACCENT_SUBTLE = "#264f78"
ACCENT_TEXT = "#75beff"

# Semantic
RED_BG = "#3b1219"
RED_BORDER = "#8b2e2e"
RED_TEXT = "#f48771"

AMBER_BG = "#3a2f00"
AMBER_BORDER = "#8a6d00"
AMBER_TEXT = "#dcdcaa"

BLUE_BG = "#1a2a3a"
BLUE_BORDER = "#264f78"
BLUE_TEXT = "#9cdcfe"

GREEN_TEXT = "#4ec9b0"

PANEL_BG = BG_PANEL
PANEL_BORDER = BORDER

# Legacy aliases used across views
SLATE_950 = BG_SIDEBAR
SLATE_900 = BG_WINDOW
SLATE_800 = BG_ELEVATED
SLATE_700 = BORDER
SLATE_600 = BORDER
SLATE_500 = TEXT_MUTED
SLATE_400 = TEXT_SECONDARY
SLATE_300 = TEXT_PRIMARY
SLATE_200 = TEXT_PRIMARY
SLATE_100 = "#ffffff"

EMERALD_950 = ACCENT_SUBTLE
EMERALD_600 = ACCENT
EMERALD_500 = ACCENT_HOVER
EMERALD_400 = ACCENT_TEXT

RED_950 = RED_BG
RED_800 = RED_BORDER
RED_400 = RED_TEXT
RED_200 = RED_TEXT

AMBER_950 = AMBER_BG
AMBER_800 = AMBER_BORDER
AMBER_300 = AMBER_TEXT

BLUE_950 = BLUE_BG
BLUE_800 = BLUE_BORDER
BLUE_300 = BLUE_TEXT


def panel_style() -> str:
    return (
        f"background-color: {BG_PANEL};"
        f"border: 1px solid {BORDER};"
        "border-radius: 10px;"
    )


def hint_style(color: str = TEXT_MUTED) -> str:
    return f"color: {color}; font-size: 12px;"


def header_panel_style() -> str:
    return (
        f"padding: 10px 12px;"
        f"background-color: {BG_ELEVATED};"
        f"border: 1px solid {BORDER};"
        "border-radius: 8px;"
        f"color: {TEXT_PRIMARY};"
    )


def meta_panel_style() -> str:
    return (
        f"padding: 10px 12px;"
        f"background-color: {BG_SIDEBAR};"
        f"border: 1px solid {BORDER};"
        "border-radius: 10px;"
        f"color: {TEXT_SECONDARY};"
    )


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_ELEVATED))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_ELEVATED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT_TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(palette)

    font = QFont()
    for family in ("Segoe UI", "Malgun Gothic", "sans-serif"):
        font.setFamily(family)
        if font.exactMatch() or family != "sans-serif":
            break
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(_STYLESHEET)


_STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {BG_WINDOW};
    color: {TEXT_PRIMARY};
}}

QStackedWidget#mainStack {{
    background-color: transparent;
}}

QWidget {{
    color: {TEXT_PRIMARY};
}}

QFrame#cardPanel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QLabel#cardTitle {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 600;
    padding: 2px 0;
}}

QLabel#sectionLabel {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
}}

QLabel#pageTitle {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 700;
}}

QLabel#mutedLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

QLabel#accentLabel {{
    color: {ACCENT_TEXT};
    font-weight: 600;
}}

QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 10px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_SECONDARY};
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background-color: {BG_PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {ACCENT_TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
    background-color: {BG_HOVER};
}}

QPushButton {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 1.2em;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: #4e4e52;
}}
QPushButton:pressed {{
    background-color: {BG_SIDEBAR};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_PANEL};
    border-color: {BORDER_SUBTLE};
}}
QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: #ffffff;
    border: 1px solid {ACCENT_HOVER};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QPushButton#linkButton {{
    background-color: transparent;
    color: {ACCENT_TEXT};
    border: none;
    padding: 4px 8px;
    font-size: 11px;
}}
QPushButton#linkButton:hover {{
    text-decoration: underline;
    background-color: transparent;
}}

QPushButton#modeBtn {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 14px;
    min-width: 48px;
}}
QPushButton#modeBtn:checked {{
    background-color: {ACCENT};
    color: #ffffff;
    border-color: {ACCENT_HOVER};
}}

QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SUBTLE};
    selection-color: {ACCENT_TEXT};
}}

QTableWidget, QTableView {{
    background-color: {BG_PANEL};
    alternate-background-color: {BG_SIDEBAR};
    gridline-color: {BORDER_SUBTLE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_SUBTLE};
    selection-color: {ACCENT_TEXT};
}}
QHeaderView::section {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER_SUBTLE};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QListWidget {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid {BORDER_SUBTLE};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_SUBTLE};
    color: {ACCENT_TEXT};
    border-left: 3px solid {ACCENT};
}}
QListWidget::item:hover:!selected {{
    background-color: {BG_HOVER};
}}

QProgressBar {{
    background-color: {BG_ELEVATED};
    border: none;
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 6px;
}}

QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {TEXT_SECONDARY};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background-color: {BG_INPUT};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT_HOVER};
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}

QScrollBar:vertical {{
    background: {BG_SIDEBAR};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4e4e52;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #5a5a5e;
}}
QScrollBar:horizontal {{
    background: {BG_SIDEBAR};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #4e4e52;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}

QStatusBar {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
QStatusBar:hover {{
    background-color: {BG_HOVER};
}}

QSplitter::handle {{
    background-color: {BORDER};
}}

QWidget#sidebarNav {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}

QFrame#sidebarFooter {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QPushButton#navBtnActive {{
    background-color: {ACCENT_SUBTLE};
    color: {ACCENT_TEXT};
    border: none;
    border-left: 4px solid {ACCENT};
    border-radius: 8px;
    text-align: left;
    padding: 8px 10px;
    font-weight: 600;
}}
QPushButton#navBtnIdle {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-left: 4px solid transparent;
    border-radius: 8px;
    text-align: left;
    padding: 8px 10px;
}}
QPushButton#navBtnIdle:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
"""
