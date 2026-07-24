from __future__ import annotations

import os

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from gui.sidebar_nav import SidebarNav

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_sidebar_navigation_matches_directive_sections(qapp) -> None:
    nav = SidebarNav()
    try:
        expected = {
            0: "Dashboard",
            1: "Achievement Records",
            2: "Player Stats",
            3: "Achievement Predictions",
            4: "Streak Records",
            5: "Record Import Center",
            6: "Manual Records",
            7: "Rating Editor",
            8: "Settings",
            9: "Advanced Tools",
        }
        assert set(nav._buttons) == set(expected)
        for index, label in expected.items():
            assert nav._buttons[index].accessibleName() == tr(label)
        assert SidebarNav.SETUP_PAGE_INDEX == 8
        assert SidebarNav.ADVANCED_TOOLS_PAGE_INDEX == 9
    finally:
        nav.deleteLater()


def test_sidebar_all_pages_remain_keyboard_accessible_at_narrow_width(qapp) -> None:
    nav = SidebarNav()
    try:
        nav.resize(200, 768)
        for index, button in nav._buttons.items():
            nav.set_current_index(index, emit=False)
            assert nav.current_index() == index
            assert button.focusPolicy().name == "StrongFocus"
            assert not button.isHidden()
    finally:
        nav.deleteLater()
