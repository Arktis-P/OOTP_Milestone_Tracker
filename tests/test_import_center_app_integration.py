from __future__ import annotations

import os

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from gui.app import MainWindow
from gui.sidebar_nav import SidebarNav

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_sidebar_indices_keep_import_center_and_hidden_baseline_page(qapp, tmp_path) -> None:
    window = MainWindow()
    try:
        assert SidebarNav.SETUP_PAGE_INDEX == 8
        assert SidebarNav.ADVANCED_TOOLS_PAGE_INDEX == 9
        assert window._stack.indexOf(window._import_center_view) == 5
        assert window._stack.indexOf(window._manual_records_page) == 6
        assert window._stack.indexOf(window._advanced_tools_view) == 9
        assert window._stack.indexOf(window._initial_import_view) > 9
    finally:
        window.close()


def test_dashboard_import_center_signal_is_connected(qapp) -> None:
    window = MainWindow()
    try:
        window._dashboard_view.navigate_to_import_center.emit()
        assert window._stack.currentWidget() is window._import_center_view
    finally:
        window.close()


class _DummyImportCenter:
    def __init__(self):
        self.completed_calls = []

    def set_completed_summary(self, totals, unresolved=None):
        self.completed_calls.append((totals, unresolved or {}))


class _DummyMain:
    def __init__(self):
        self._import_center_view = _DummyImportCenter()
        self.refreshed = []
        self.data_refreshed = self

    def _update_status_message(self):
        self.status_updated = True

    def emit(self, kind):
        self.refreshed.append(kind)


def test_boxscore_finish_updates_import_center_summary_and_refresh_signal(qapp) -> None:
    dummy = _DummyMain()

    MainWindow._on_boxscore_import_finished(dummy, "3 games added · 1 milestone")

    totals, unresolved = dummy._import_center_view.completed_calls[-1]
    assert totals["detail"] == "3 games added · 1 milestone"
    assert totals["workflow"] == tr("latest games")
    assert unresolved == {}
    assert dummy.refreshed == ["boxscore"]


def test_initial_import_finish_updates_import_center_next_action(qapp) -> None:
    dummy = _DummyMain()

    MainWindow._on_init_import_finished(dummy)

    totals, unresolved = dummy._import_center_view.completed_calls[-1]
    assert totals["workflow"] == tr("career and historical records")
    assert totals["status"] == tr("completed")
    assert tr("next action") in unresolved
    assert dummy.refreshed == ["init"]
