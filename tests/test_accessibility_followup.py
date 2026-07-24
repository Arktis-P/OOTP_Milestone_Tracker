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


def test_sidebar_is_resizable_and_keyboard_accessible() -> None:
    app = qapp()
    nav = SidebarNav()
    nav.show()
    app.processEvents()

    assert nav.minimumWidth() >= 200
    assert nav.maximumWidth() > nav.minimumWidth()
    assert nav.accessibleName()
    buttons = nav.findChildren(QPushButton)
    assert buttons
    assert all(button.focusPolicy() == Qt.FocusPolicy.StrongFocus for button in buttons)
    assert all(button.accessibleName() for button in buttons)

    nav.set_current_index(2, emit=False)
    active = [button for button in buttons if button.objectName() == "navBtnActive"]
    assert len(active) == 1
    assert "selected" in active[0].accessibleDescription().lower()


def test_prediction_controls_and_detail_roles(tmp_path: Path) -> None:
    app = qapp()
    aggregator = Aggregator(tmp_path / "test.db")
    view = PredictView(
        aggregator,
        MilestoneDefinitions(batting=[], pitching=[]),
        AppSettings(current_season=2026),
    )
    detail = PlayerDetailSummary(AppSettings(current_season=2026))
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

    assert view.table.columnCount() == 7
    assert detail.meta_label.objectName() == "secondaryStat"
    assert detail.status_label.objectName() == "statusText"
    assert detail.events_list.wordWrap()
    assert detail.events_list.focusPolicy() == Qt.FocusPolicy.StrongFocus

    view.close()
    detail.close()
    aggregator.close()
