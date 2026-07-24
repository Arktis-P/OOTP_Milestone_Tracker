"""Persistent import workflow state contracts."""

from __future__ import annotations

from core.app_state import get_dashboard_import_states
from core.config.settings_manager import AppSettings
from core.import_workflow import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    STEP_ANALYZE_CLASSIFY,
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    advance_import_workflow,
    finish_import_workflow,
    load_import_workflow_state,
    start_import_workflow,
)
from core.stats.aggregator import Aggregator


def test_workflow_state_survives_database_reopen(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    aggregator = Aggregator(db_path)
    try:
        start_import_workflow(
            aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            message="Scanning messages",
        )
        advance_import_workflow(
            aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            current_step=STEP_ANALYZE_CLASSIFY,
            totals={"processed": 3},
            unresolved={"date_missing": 1},
            message="Three messages classified",
        )
        finish_import_workflow(
            aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            outcome=OUTCOME_COMPLETED,
            totals={"created": 2, "duplicates": 1},
            unresolved={"date_missing": 0},
            report_ref="message-run-1",
        )
        aggregator.conn.commit()
        aggregator.reopen()

        restored = load_import_workflow_state(aggregator.conn, WORKFLOW_NEWS_MESSAGES)

        assert restored.current_step == "confirm_result"
        assert restored.outcome == OUTCOME_COMPLETED
        assert restored.totals["processed"] == 3
        assert restored.totals["created"] == 2
        assert restored.totals["duplicates"] == 1
        assert restored.unresolved["date_missing"] == 0
        assert restored.report_ref == "message-run-1"
        assert restored.completed_at is not None
    finally:
        aggregator.close()


def test_workflows_are_independent_from_legacy_last_import_at(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "workflow.db")
    try:
        settings = AppSettings(
            active_save_path=str(tmp_path / "league.lg"),
            paths={"boxscore_dir": str(tmp_path / "box_scores")},
            import_state={"last_import_at": "2026-07-24T00:00:00+00:00"},
        )

        states = {item.key: item.workflow for item in get_dashboard_import_states(settings, aggregator)}

        assert states[WORKFLOW_LATEST_BOXSCORES].outcome == OUTCOME_COMPLETED
        assert states[WORKFLOW_LATEST_BOXSCORES].completed_at == "2026-07-24T00:00:00+00:00"
        assert states[WORKFLOW_NEWS_MESSAGES].outcome is None
        assert states[WORKFLOW_NEWS_MESSAGES].started_at is None
    finally:
        aggregator.close()


def test_failed_and_cancelled_are_terminal_not_completed(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "workflow.db")
    try:
        finish_import_workflow(
            aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            outcome=OUTCOME_FAILED,
            totals={"errors": 1},
        )
        failed = load_import_workflow_state(aggregator.conn, WORKFLOW_NEWS_MESSAGES)
        assert failed.is_terminal
        assert failed.outcome == OUTCOME_FAILED
        assert failed.outcome != OUTCOME_COMPLETED

        finish_import_workflow(
            aggregator.conn,
            WORKFLOW_LATEST_BOXSCORES,
            outcome=OUTCOME_CANCELLED,
        )
        cancelled = load_import_workflow_state(aggregator.conn, WORKFLOW_LATEST_BOXSCORES)
        assert cancelled.is_terminal
        assert cancelled.outcome == OUTCOME_CANCELLED
        assert cancelled.outcome != OUTCOME_COMPLETED
    finally:
        aggregator.close()
