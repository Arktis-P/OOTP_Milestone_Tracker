from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton

from core.config import AppSettings
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from gui.sidebar_nav import SidebarNav
from gui.views.predict_view import PredictView
from gui.widgets.player_detail_summary import PlayerDetailSummary


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_sidebar_nav_has_keyboard_and_status_accessibility() -> None:
    app = qapp()
    nav = SidebarNav()
    nav.show()
    app.processEvents()

    assert nav.minimumWidth() >= 200
    assert nav.accessibleName()
    buttons = nav.findChildren(QPushButton)
    assert buttons
    for button in buttons:
        assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert button.accessibleName()
        assert "open" in button.accessibleDescription().lower()

    nav.set_current_index(2, emit=False)
    active = [button for button in buttons if button.objectName() == "navBtnActive"]
    assert len(active) == 1
    assert "selected" in active[0].accessibleDescription().lower()

    nav.set_status(level="warning", status_text="Needs setup", context_text="Open Settings")
    assert nav._footer.accessibleName()
    assert "warning" in nav._footer.accessibleDescription().lower()

    nav.close()


def test_predict_view_controls_are_named_and_focusable(tmp_path: Path) -> None:
    app = qapp()
    aggregator = Aggregator(tmp_path / "test.db")
    view = PredictView(
        aggregator,
        MilestoneDefinitions(batting=[], pitching=[]),
        AppSettings(current_season=2026),
    )
    view.show()
    app.processEvents()

    for widget in (
        view.refresh_button,
        view.player_filter,
        view.grade_filter,
        view.near_only_checkbox,
        view.table,
    ):
        assert widget.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert widget.accessibleName()
        assert widget.accessibleDescription() or widget.toolTip()

    assert view.table.toolTip()
    view.close()
    aggregator.close()


def test_player_detail_summary_uses_text_roles_and_wraps() -> None:
    app = qapp()
    widget = PlayerDetailSummary(AppSettings(current_season=2026))
    widget.show()
    widget.clear()
    app.processEvents()

    assert widget.meta_label.objectName() == "secondaryStat"
    assert widget.status_label.objectName() == "statusText"
    assert widget.events_list.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert widget.events_list.wordWrap()
    assert widget.events_list.minimumHeight() >= 118
    assert widget.streaks_label.objectName() == "helperText"
    assert widget.next_label.objectName() == "helperText"
    assert widget.status_label.isVisible()
    assert widget.status_label.accessibleName()

    widget.close()
