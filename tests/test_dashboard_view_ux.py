from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from gui.views.dashboard_view import DashboardView
from gui.views.import_center_view import ImportCenterView
from gui.widgets.import_workflow_status import (
    IMPORT_WORKFLOW_STEPS,
    ImportResultSummary,
    WorkflowStatusPanel,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeAggregator:
    is_closed = True
    db_path = ""


class FakeMilestones:
    def get_by_key(self, _key):
        return None


class FakeSettings:
    active_save = "Test League"
    current_season = 2026
    import_mlb_only = True
    boxscore_dir = "C:/ootp/boxscores"
    initial_stats_dir = "C:/ootp/import"
    season_games_total = 162
    tracked_teams = []
    custom_mlb_teams = []
    import_state = {"last_import_at": "2026-07-23T10:00:00"}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dashboard(qapp):
    view = DashboardView(FakeAggregator(), FakeMilestones(), FakeSettings(), SimpleNamespace(save=lambda _settings: None))
    yield view
    view.deleteLater()


def test_dashboard_exposes_six_step_workflow_panel(dashboard) -> None:
    assert isinstance(dashboard.workflow_panel, WorkflowStatusPanel)
    assert dashboard.workflow_panel.row_count() == 6


def test_dashboard_workflow_actions_preserve_navigation_signals(dashboard) -> None:
    captured: list[str] = []
    dashboard.navigate_to_import_center.connect(lambda: captured.append("import_center"))
    dashboard.navigate_to_milestone.connect(lambda _payload: captured.append("milestone"))
    dashboard.navigate_to_settings.connect(lambda: captured.append("settings"))
    dashboard.navigate_to_review_filter.connect(lambda _key: captured.append("filter"))

    dashboard._on_workflow_action("baseline_records")
    dashboard._on_workflow_action("record_exceptions")
    dashboard._on_workflow_action("league_tracking")

    assert captured == ["import_center", "filter", "settings"]


def test_dashboard_workflow_panel_survives_narrow_width(dashboard) -> None:
    dashboard.resize(QSize(900, 650))
    dashboard.workflow_panel.setMaximumWidth(900)

    assert dashboard.workflow_panel.row_count() == 6
    assert dashboard.workflow_panel.sizeHint().height() > 0


def test_import_center_has_three_import_cards_and_shared_five_step_model(qapp) -> None:
    view = ImportCenterView()
    try:
        cards = [view.latest_games_card, view.message_card, view.baseline_card]

        assert [card.key for card in cards] == ["latest_boxscores", "news_messages", "baseline_history"]
        assert all(card.status_panel.row_count() == len(IMPORT_WORKFLOW_STEPS) for card in cards)
    finally:
        view.deleteLater()


def test_import_center_keeps_completion_partial_and_error_summaries(qapp) -> None:
    view = ImportCenterView()
    try:
        view.set_result_summary(
            ImportResultSummary(
                outcome="complete",
                headline="Record import completed.",
                totals={"games": 42, "messages": 18, "records": 7},
                unresolved={"excluded": 8, "duplicates": 2},
                actions=("View records", "Review issues", "Check errors"),
            )
        )
        assert "Record import completed" in view.result_summary.headline_label.text()
        assert "games 42" in view.result_summary.detail_label.text()

        view.set_partial_success_summary(
            {"games": 42, "messages": 18},
            {"date review": 1, "errors": 2},
        )
        assert view.result_summary.headline_label.text() == tr(
            "Record import partially completed. Some items need review."
        )
        assert "errors 2" in view.result_summary.detail_label.text()

        view.set_error_summary("source files missing")
        assert "source files missing" in view.result_summary.headline_label.text()
    finally:
        view.deleteLater()


def test_import_center_workflow_actions_emit_card_and_step(qapp) -> None:
    view = ImportCenterView()
    captured: list[tuple[str, str]] = []
    try:
        view.workflow_action_requested.connect(lambda card, step: captured.append((card, step)))
        view.latest_games_card.action_requested.emit("latest_boxscores", "source_check")

        assert captured == [("latest_boxscores", "source_check")]
    finally:
        view.deleteLater()
