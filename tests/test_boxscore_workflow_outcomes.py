from __future__ import annotations

from core.import_workflow import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL_SUCCESS,
)
from core.stats.models import BatchImportResult, ImportResult
from gui.workers.import_worker import ImportFinishedPayload


def test_boxscore_payload_completed_without_errors() -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(imported=3, total_scanned=3),
        milestones_recorded=2,
    )

    assert payload.outcome == OUTCOME_COMPLETED
    assert payload.processed == 3
    assert payload.created == 5
    assert payload.duplicates == 0
    assert payload.excluded == 0
    assert payload.errors == 0
    assert payload.unresolved == {}


def test_boxscore_payload_partial_success_when_success_and_errors_mix() -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(
            imported=1,
            total_scanned=3,
            skipped_existing=1,
            skipped_non_mlb=1,
            errors=[ImportResult(game_id=1001, error="bad html")],
        )
    )

    assert payload.outcome == OUTCOME_PARTIAL_SUCCESS
    assert payload.processed == 3
    assert payload.created == 1
    assert payload.duplicates == 1
    assert payload.excluded == 1
    assert payload.errors == 1
    assert payload.unresolved == {"errors": 1}


def test_boxscore_payload_failed_when_errors_have_no_success() -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(
            total_scanned=1,
            errors=[ImportResult(game_id=0, error="folder unavailable")],
        )
    )

    assert payload.outcome == OUTCOME_FAILED
    assert payload.processed == 1
    assert payload.created == 0
    assert payload.errors == 1
    assert payload.unresolved == {"errors": 1}


def test_boxscore_payload_cancelled_retains_totals() -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(imported=2, total_scanned=5, skipped_existing=1),
        outcome=OUTCOME_CANCELLED,
        message="cancelled by user",
    )

    assert payload.outcome == OUTCOME_CANCELLED
    assert payload.processed == 5
    assert payload.created == 2
    assert payload.duplicates == 1
    assert payload.errors == 0
    assert payload.message == "cancelled by user"
