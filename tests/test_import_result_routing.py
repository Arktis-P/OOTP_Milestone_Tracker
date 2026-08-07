from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.config.settings_manager import AppSettings, SettingsManager
from core.import_workflow import (
    OUTCOME_FAILED,
    WORKFLOW_BASELINE_HISTORY,
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    WORKFLOW_SEASON_FINALIZE,
    finish_import_workflow,
)
from gui.app import MainWindow
from gui.views.message_review_view import MessageReviewView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path: Path):
    settings = AppSettings(
        db_path=str(tmp_path / "records.db"),
        milestones_path=str(ROOT / "data" / "milestones.csv"),
        current_season=2026,
    )
    widget = MainWindow(settings, SettingsManager(tmp_path / "settings.json"))
    yield widget
    widget.close()


@pytest.mark.parametrize(
    ("workflow_id", "source"),
    [
        (WORKFLOW_LATEST_BOXSCORES, "boxscore_auto"),
        (WORKFLOW_NEWS_MESSAGES, "message_auto"),
        (WORKFLOW_SEASON_FINALIZE, "season_final"),
    ],
)
def test_view_records_routes_to_matching_source_filter(
    window: MainWindow, workflow_id: str, source: str
) -> None:
    window._on_import_center_result_action(workflow_id, "view_records")

    assert window._stack.currentWidget() is window._milestone_view
    assert window._milestone_view.source_combo.currentData() == source


def test_baseline_differences_route_to_baseline_screen(window: MainWindow) -> None:
    window._on_import_center_result_action(
        WORKFLOW_BASELINE_HISTORY, "view_differences"
    )
    assert window._stack.currentWidget() is window._initial_import_view


def test_news_errors_route_to_error_filter(window: MainWindow) -> None:
    review = MessageReviewView([])
    window._stack.addWidget(review)
    window._message_review_view = review

    window._on_import_center_result_action(WORKFLOW_NEWS_MESSAGES, "view_errors")

    assert window._stack.currentWidget() is review
    assert review.filter_combo.currentData() == "error"


def test_persisted_error_is_available_after_in_memory_dialog_is_gone(
    window: MainWindow, monkeypatch
) -> None:
    finish_import_workflow(
        window._aggregator.conn,
        WORKFLOW_LATEST_BOXSCORES,
        outcome=OUTCOME_FAILED,
        unresolved={"errors": 1},
        message="bad source file",
        report_ref="reports/latest_boxscores_last_errors.json",
    )
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: shown.append(message),
    )

    window._on_import_center_result_action(
        WORKFLOW_LATEST_BOXSCORES, "view_errors"
    )

    assert shown and "bad source file" in shown[0]
    assert "latest_boxscores_last_errors.json" in shown[0]

