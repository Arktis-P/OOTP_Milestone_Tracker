"""Prototype-inspired dark theme (slate + emerald) for PyQt6."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

# Tailwind slate / emerald palette (prototype HTML)
SLATE_950 = "#020617"
SLATE_900 = "#0f172a"
SLATE_800 = "#1e293b"
SLATE_700 = "#334155"
SLATE_600 = "#475569"
SLATE_500 = "#64748b"
SLATE_400 = "#94a3b8"
SLATE_300 = "#cbd5e1"
SLATE_200 = "#e2e8f0"
SLATE_100 = "#f1f5f9"

EMERALD_950 = "#022c22"
EMERALD_600 = "#059669"
EMERALD_500 = "#10b981"
EMERALD_400 = "#34d399"

RED_950 = "#450a0a"
RED_800 = "#991b1b"
RED_400 = "#f87171"
RED_200 = "#fecaca"

AMBER_950 = "#451a03"
AMBER_800 = "#92400e"
AMBER_300 = "#fcd34d"

BLUE_950 = "#172554"
BLUE_800 = "#1e40af"
BLUE_300 = "#93c5fd"

PANEL_BG = SLATE_900
PANEL_BORDER = SLATE_800
CONTENT_BG = "#0f172a66"  # slate-900/40 feel on QWidget


def panel_style() -> str:
    return (
        f"background-color: {PANEL_BG};"
        f"border: 1px solid {PANEL_BORDER};"
        "border-radius: 10px;"
    )


def hint_style(color: str = SLATE_500) -> str:
    return f"color: {color}; font-size: 12px;"


def header_panel_style() -> str:
    return (
        f"padding: 8px;"
        f"background-color: {SLATE_800};"
        f"border: 1px solid {PANEL_BORDER};"
        "border-radius: 8px;"
        f"color: {SLATE_200};"
    )


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(SLATE_900))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(SLATE_200))
    palette.setColor(QPalette.ColorRole.Base, QColor(SLATE_950))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SLATE_800))
    palette.setColor(QPalette.ColorRole.Text, QColor(SLATE_200))
    palette.setColor(QPalette.ColorRole.Button, QColor(SLATE_800))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(SLATE_200))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(EMERALD_600))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(SLATE_100))
    palette.setColor(QPalette.ColorRole.Link, QColor(EMERALD_400))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(SLATE_500))
    app.setPalette(palette)

    font = QFont()
    for family in ("Pretendard", "Malgun Gothic", "Segoe UI", "sans-serif"):
        font.setFamily(family)
        if font.exactMatch() or family in ("Malgun Gothic", "Segoe UI"):
            break
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(_STYLESHEET)


_STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {SLATE_900};
    color: {SLATE_200};
}}

QStackedWidget#mainStack {{
    background-color: transparent;
}}

QWidget {{
    color: {SLATE_200};
}}

QGroupBox {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    border-radius: 10px;
    margin-top: 10px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {SLATE_300};
}}

QTabWidget::pane {{
    border: 1px solid {PANEL_BORDER};
    border-radius: 8px;
    background-color: {PANEL_BG};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {SLATE_950};
    color: {SLATE_400};
    border: 1px solid {PANEL_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {PANEL_BG};
    color: {EMERALD_400};
    border-bottom: 2px solid {EMERALD_500};
}}
QTabBar::tab:hover:!selected {{
    color: {SLATE_200};
    background-color: {SLATE_800};
}}

QPushButton {{
    background-color: {SLATE_800};
    color: {SLATE_200};
    border: 1px solid {SLATE_700};
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 1.2em;
}}
QPushButton:hover {{
    background-color: {SLATE_700};
    border-color: {SLATE_600};
}}
QPushButton:pressed {{
    background-color: {SLATE_950};
}}
QPushButton:disabled {{
    color: {SLATE_600};
    background-color: {SLATE_900};
    border-color: {SLATE_800};
}}
QPushButton#primaryButton {{
    background-color: {EMERALD_600};
    color: white;
    border: 1px solid {EMERALD_500};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {EMERALD_500};
}}
QPushButton#primaryButton:pressed {{
    background-color: #047857;
}}

QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {SLATE_950};
    color: {SLATE_200};
    border: 1px solid {PANEL_BORDER};
    border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: {EMERALD_600};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border-color: {EMERALD_500};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {SLATE_950};
    color: {SLATE_200};
    border: 1px solid {PANEL_BORDER};
    selection-background-color: {EMERALD_950};
    selection-color: {EMERALD_400};
}}

QTableWidget, QTableView {{
    background-color: {PANEL_BG};
    alternate-background-color: {SLATE_950};
    gridline-color: {SLATE_800};
    border: 1px solid {PANEL_BORDER};
    border-radius: 8px;
    selection-background-color: {EMERALD_950};
    selection-color: {EMERALD_400};
}}
QHeaderView::section {{
    background-color: {SLATE_950};
    color: {SLATE_400};
    border: none;
    border-bottom: 1px solid {PANEL_BORDER};
    border-right: 1px solid {SLATE_800};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QListWidget {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {SLATE_800};
}}
QListWidget::item:selected {{
    background-color: {EMERALD_950};
    color: {EMERALD_400};
    border-left: 3px solid {EMERALD_500};
}}
QListWidget::item:hover:!selected {{
    background-color: {SLATE_800};
}}

QProgressBar {{
    background-color: {SLATE_800};
    border: none;
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {EMERALD_500};
    border-radius: 6px;
}}

QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {SLATE_300};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {SLATE_600};
    background-color: {SLATE_950};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {EMERALD_600};
    border-color: {EMERALD_500};
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}

QScrollBar:vertical {{
    background: {SLATE_950};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SLATE_700};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {SLATE_600};
}}
QScrollBar:horizontal {{
    background: {SLATE_950};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {SLATE_700};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}

QStatusBar {{
    background-color: {SLATE_950};
    color: {SLATE_400};
    border-top: 1px solid {PANEL_BORDER};
    font-size: 11px;
}}
QStatusBar:hover {{
    background-color: #0f172a99;
}}

QSplitter::handle {{
    background-color: {PANEL_BORDER};
}}

QLabel#mutedLabel {{
    color: {SLATE_500};
}}
QLabel#accentLabel {{
    color: {EMERALD_400};
    font-weight: 600;
}}
"""
