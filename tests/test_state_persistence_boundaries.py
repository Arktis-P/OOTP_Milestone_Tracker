"""Durability boundaries for import workflows and processed messages."""

from __future__ import annotations

from core.import_workflow import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL_SUCCESS,
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    advance_import_workflow,
    finish_import_workflow,
    load_import_workflow_state,
    start_import_workflow,
)
from core.milestone.message_automation.processed import (
    fingerprint_message_text,
    get_message_rescan_status,
    upsert_processed_message,
)
from core.stats.aggregator import Aggregator


def test_workflow_state_commits_by_default_without_external_commit(tmp_path) -> None:
    db_path = tmp_path / "workflow-boundary.db"
    writer = Aggregator(db_path)
    reader = Aggregator(db_path)
    try:
        start_import_workflow(writer.conn, WORKFLOW_NEWS_MESSAGES, message="start")
        advance_import_workflow(
            writer.conn,
            WORKFLOW_NEWS_MESSAGES,
            current_step="save",
            totals={"processed": 4},
            unresolved={"date_missing": 1},
            message="saving",
        )

        restored = load_import_workflow_state(reader.conn, WORKFLOW_NEWS_MESSAGES)

        assert restored.current_step == "save"
        assert restored.totals["processed"] == 4
        assert restored.unresolved["date_missing"] == 1
    finally:
        reader.close()
        writer.close()


def test_all_terminal_outcomes_are_durable_without_external_commit(tmp_path) -> None:
    db_path = tmp_path / "workflow-outcomes.db"
    writer = Aggregator(db_path)
    reader = Aggregator(db_path)
    workflows = [
        (WORKFLOW_NEWS_MESSAGES, OUTCOME_COMPLETED),
        (WORKFLOW_LATEST_BOXSCORES, OUTCOME_PARTIAL_SUCCESS),
        ("baseline_history", OUTCOME_FAILED),
        ("season_finalize", OUTCOME_CANCELLED),
    ]
    try:
        for workflow_id, outcome in workflows:
            finish_import_workflow(
                writer.conn,
                workflow_id,
                outcome=outcome,
                totals={"processed": 1},
                unresolved={"errors": 1 if outcome == OUTCOME_FAILED else 0},
            )

        restored = {
            workflow_id: load_import_workflow_state(reader.conn, workflow_id).outcome
            for workflow_id, _outcome in workflows
        }

        assert restored == dict(workflows)
    finally:
        reader.close()
        writer.close()


def test_commit_false_keeps_workflow_changes_inside_caller_transaction(tmp_path) -> None:
    db_path = tmp_path / "workflow-transaction.db"
    writer = Aggregator(db_path)
    reader = Aggregator(db_path)
    try:
        # Initialize the reader-side schema before opening the writer's
        # uncommitted transaction; CREATE TABLE under a concurrent writer
        # would test SQLite DDL locking rather than the commit contract.
        load_import_workflow_state(reader.conn, WORKFLOW_NEWS_MESSAGES)
        start_import_workflow(
            writer.conn,
            WORKFLOW_NEWS_MESSAGES,
            message="private",
            commit=False,
        )

        assert (
            reader.conn.execute(
                "SELECT started_at FROM import_workflow_state WHERE workflow_id = ?",
                (WORKFLOW_NEWS_MESSAGES,),
            ).fetchone()
            is None
        )

        writer.conn.commit()
        assert load_import_workflow_state(reader.conn, WORKFLOW_NEWS_MESSAGES).started_at is not None
    finally:
        reader.close()
        writer.close()


def test_processed_message_commits_by_default_and_rescan_statuses_survive_reopen(tmp_path) -> None:
    db_path = tmp_path / "processed-boundary.db"
    writer = Aggregator(db_path)
    reader = Aggregator(db_path)
    try:
        applied = fingerprint_message_text("applied", source_id="message1", source_mtime=1.0)
        excluded = fingerprint_message_text("excluded", source_id="message2", source_mtime=1.0)

        upsert_processed_message(
            writer.conn,
            fingerprint=applied,
            status="applied",
            created_record_ids=[10],
            mark_applied=True,
        )
        upsert_processed_message(
            writer.conn,
            fingerprint=excluded,
            status="excluded",
            exclusion_reason="excluded_by_reviewer",
        )

        assert get_message_rescan_status(reader.conn, applied) == "already_applied"
        assert get_message_rescan_status(reader.conn, excluded) == "excluded"
        changed = fingerprint_message_text("changed", source_id="message2", source_mtime=2.0)
        assert get_message_rescan_status(reader.conn, changed) == "changed_review_needed"
    finally:
        reader.close()
        writer.close()


def test_commit_false_keeps_processed_message_inside_caller_transaction(tmp_path) -> None:
    db_path = tmp_path / "processed-transaction.db"
    writer = Aggregator(db_path)
    reader = Aggregator(db_path)
    try:
        fingerprint = fingerprint_message_text("candidate", source_id="message3")
        get_message_rescan_status(reader.conn, fingerprint)
        upsert_processed_message(
            writer.conn,
            fingerprint=fingerprint,
            status="candidate",
            commit=False,
        )

        assert (
            reader.conn.execute(
                "SELECT status FROM processed_messages WHERE source_id = ?",
                (fingerprint.source_id,),
            ).fetchone()
            is None
        )

        writer.conn.commit()
        assert get_message_rescan_status(reader.conn, fingerprint) == "candidate"
    finally:
        reader.close()
        writer.close()
