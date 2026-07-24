"""Persistent import workflow state shared by dashboard/import-center UI.

The project already stores legacy boxscore timestamps in
``settings.import_state``.  This module adds a small DB-backed state contract
without changing the central schema migration file so callers can persist and
restore each import task independently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

WORKFLOW_LATEST_BOXSCORES = "latest_boxscores"
WORKFLOW_NEWS_MESSAGES = "news_messages"
WORKFLOW_BASELINE_HISTORY = "baseline_history"
WORKFLOW_SEASON_FINALIZE = "season_finalize"

WORKFLOW_IDS = (
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    WORKFLOW_BASELINE_HISTORY,
    WORKFLOW_SEASON_FINALIZE,
)

STEP_SOURCE_CHECK = "source_check"
STEP_ANALYZE_CLASSIFY = "analyze_classify"
STEP_REVIEW_RESULTS = "review_results"
STEP_SAVE = "save"
STEP_CONFIRM_RESULT = "confirm_result"

WORKFLOW_STEPS = (
    STEP_SOURCE_CHECK,
    STEP_ANALYZE_CLASSIFY,
    STEP_REVIEW_RESULTS,
    STEP_SAVE,
    STEP_CONFIRM_RESULT,
)

OUTCOME_COMPLETED = "completed"
OUTCOME_PARTIAL_SUCCESS = "partial_success"
OUTCOME_FAILED = "failed"
OUTCOME_CANCELLED = "cancelled"

TERMINAL_OUTCOMES = (
    OUTCOME_COMPLETED,
    OUTCOME_PARTIAL_SUCCESS,
    OUTCOME_FAILED,
    OUTCOME_CANCELLED,
)

COUNT_KEYS = (
    "processed",
    "created",
    "duplicates",
    "excluded",
    "date_missing",
    "errors",
)


@dataclass(frozen=True)
class ImportWorkflowState:
    workflow_id: str
    current_step: str = STEP_SOURCE_CHECK
    outcome: str | None = None
    totals: dict[str, int] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    message: str = ""
    report_ref: str = ""

    @property
    def is_running(self) -> bool:
        return bool(self.started_at and self.outcome is None)

    @property
    def is_terminal(self) -> bool:
        return self.outcome in TERMINAL_OUTCOMES

    def can_analyze(self) -> bool:
        return self.current_step == STEP_SOURCE_CHECK and self.outcome is None

    def can_review(self) -> bool:
        return self.current_step == STEP_REVIEW_RESULTS and self.outcome is None

    def can_save(self) -> bool:
        return self.current_step == STEP_SAVE and self.outcome is None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_import_workflow_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_workflow_state (
            workflow_id     TEXT PRIMARY KEY,
            current_step    TEXT NOT NULL,
            outcome         TEXT,
            totals_json     TEXT NOT NULL DEFAULT '{}',
            unresolved_json TEXT NOT NULL DEFAULT '{}',
            started_at      TEXT,
            completed_at    TEXT,
            message         TEXT NOT NULL DEFAULT '',
            report_ref      TEXT NOT NULL DEFAULT '',
            updated_at      TEXT DEFAULT (datetime('now'))
        )
        """
    )


def default_totals() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def normalize_workflow_id(workflow_id: str) -> str:
    if workflow_id not in WORKFLOW_IDS:
        raise ValueError(f"Unsupported import workflow: {workflow_id!r}")
    return workflow_id


def normalize_step(step: str) -> str:
    if step not in WORKFLOW_STEPS:
        raise ValueError(f"Unsupported workflow step: {step!r}")
    return step


def normalize_outcome(outcome: str | None) -> str | None:
    if outcome is not None and outcome not in TERMINAL_OUTCOMES:
        raise ValueError(f"Unsupported workflow outcome: {outcome!r}")
    return outcome


def load_import_workflow_state(conn: Any, workflow_id: str) -> ImportWorkflowState:
    workflow_id = normalize_workflow_id(workflow_id)
    ensure_import_workflow_schema(conn)
    row = conn.execute(
        """
        SELECT workflow_id, current_step, outcome, totals_json, unresolved_json,
               started_at, completed_at, message, report_ref
        FROM import_workflow_state
        WHERE workflow_id = ?
        """,
        (workflow_id,),
    ).fetchone()
    if row is None:
        return ImportWorkflowState(workflow_id=workflow_id, totals=default_totals())
    data = dict(row) if hasattr(row, "keys") else {
        "workflow_id": row[0],
        "current_step": row[1],
        "outcome": row[2],
        "totals_json": row[3],
        "unresolved_json": row[4],
        "started_at": row[5],
        "completed_at": row[6],
        "message": row[7],
        "report_ref": row[8],
    }
    return ImportWorkflowState(
        workflow_id=data["workflow_id"],
        current_step=data["current_step"],
        outcome=data["outcome"],
        totals=_decode_counts(data["totals_json"]),
        unresolved=_decode_counts(data["unresolved_json"]),
        started_at=data["started_at"],
        completed_at=data["completed_at"],
        message=data["message"] or "",
        report_ref=data["report_ref"] or "",
    )


def load_all_import_workflow_states(conn: Any) -> dict[str, ImportWorkflowState]:
    ensure_import_workflow_schema(conn)
    return {
        workflow_id: load_import_workflow_state(conn, workflow_id)
        for workflow_id in WORKFLOW_IDS
    }


def save_import_workflow_state(conn: Any, state: ImportWorkflowState) -> ImportWorkflowState:
    workflow_id = normalize_workflow_id(state.workflow_id)
    current_step = normalize_step(state.current_step)
    outcome = normalize_outcome(state.outcome)
    totals = _merge_counts(default_totals(), state.totals)
    unresolved = _merge_counts(default_totals(), state.unresolved)
    ensure_import_workflow_schema(conn)
    conn.execute(
        """
        INSERT INTO import_workflow_state (
            workflow_id, current_step, outcome, totals_json, unresolved_json,
            started_at, completed_at, message, report_ref, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(workflow_id) DO UPDATE SET
            current_step = excluded.current_step,
            outcome = excluded.outcome,
            totals_json = excluded.totals_json,
            unresolved_json = excluded.unresolved_json,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            message = excluded.message,
            report_ref = excluded.report_ref,
            updated_at = excluded.updated_at
        """,
        (
            workflow_id,
            current_step,
            outcome,
            json.dumps(totals, sort_keys=True),
            json.dumps(unresolved, sort_keys=True),
            state.started_at,
            state.completed_at,
            state.message,
            state.report_ref,
        ),
    )
    return load_import_workflow_state(conn, workflow_id)


def start_import_workflow(
    conn: Any,
    workflow_id: str,
    *,
    message: str = "",
    report_ref: str = "",
) -> ImportWorkflowState:
    return save_import_workflow_state(
        conn,
        ImportWorkflowState(
            workflow_id=normalize_workflow_id(workflow_id),
            current_step=STEP_SOURCE_CHECK,
            outcome=None,
            totals=default_totals(),
            unresolved=default_totals(),
            started_at=utc_now_iso(),
            completed_at=None,
            message=message,
            report_ref=report_ref,
        ),
    )


def advance_import_workflow(
    conn: Any,
    workflow_id: str,
    *,
    current_step: str,
    totals: dict[str, int] | None = None,
    unresolved: dict[str, int] | None = None,
    message: str = "",
    report_ref: str = "",
) -> ImportWorkflowState:
    state = load_import_workflow_state(conn, workflow_id)
    if state.outcome is not None:
        raise ValueError("Terminal workflow state cannot be advanced")
    return save_import_workflow_state(
        conn,
        ImportWorkflowState(
            workflow_id=state.workflow_id,
            current_step=normalize_step(current_step),
            outcome=None,
            totals=_merge_counts(state.totals, totals or {}),
            unresolved=_merge_counts(state.unresolved, unresolved or {}),
            started_at=state.started_at or utc_now_iso(),
            completed_at=None,
            message=message or state.message,
            report_ref=report_ref or state.report_ref,
        ),
    )


def finish_import_workflow(
    conn: Any,
    workflow_id: str,
    *,
    outcome: str,
    totals: dict[str, int] | None = None,
    unresolved: dict[str, int] | None = None,
    message: str = "",
    report_ref: str = "",
) -> ImportWorkflowState:
    state = load_import_workflow_state(conn, workflow_id)
    return save_import_workflow_state(
        conn,
        ImportWorkflowState(
            workflow_id=state.workflow_id,
            current_step=STEP_CONFIRM_RESULT,
            outcome=normalize_outcome(outcome),
            totals=_merge_counts(state.totals, totals or {}),
            unresolved=_merge_counts(state.unresolved, unresolved or {}),
            started_at=state.started_at or utc_now_iso(),
            completed_at=utc_now_iso(),
            message=message or state.message,
            report_ref=report_ref or state.report_ref,
        ),
    )


def _decode_counts(raw: str | None) -> dict[str, int]:
    if not raw:
        return default_totals()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return default_totals()
    if not isinstance(data, dict):
        return default_totals()
    return _merge_counts(default_totals(), {str(k): int(v or 0) for k, v in data.items()})


def _merge_counts(base: dict[str, int], updates: dict[str, int]) -> dict[str, int]:
    merged = {str(k): int(v or 0) for k, v in base.items()}
    for key, value in updates.items():
        merged[str(key)] = int(value or 0)
    return merged
