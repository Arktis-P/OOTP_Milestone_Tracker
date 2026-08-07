from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from core.import_workflow import (
    OUTCOME_COMPLETED,
    OUTCOME_PARTIAL_SUCCESS,
    WORKFLOW_NEWS_MESSAGES,
    load_import_workflow_state,
    start_import_workflow,
)
from core.milestone.message_automation.parser import parse_message
from core.milestone.message_automation.processed import (
    fingerprint_message_text,
    get_message_rescan_status,
)
from core.stats.aggregator import Aggregator
from gui.app import MainWindow
from gui.widgets.message_review_model import (
    STATUS_EXCLUDED,
    MessageReviewItem,
    MessageReviewModel,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "messages"
    / "trade_simple_01.txt"
)


def _dummy(aggregator: Aggregator, item: MessageReviewItem) -> SimpleNamespace:
    return SimpleNamespace(
        _aggregator=aggregator,
        _message_review_view=SimpleNamespace(model=MessageReviewModel([item])),
        _import_center_view=None,
        _refresh_import_workflow_views=lambda: None,
    )


def test_reviewer_exclusion_is_durable_and_changed_source_requires_review(
    tmp_path: Path,
) -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    parsed = parse_message(
        raw,
        tracked_teams=[],
        message_date=date(2026, 5, 1),
        season_hint=2026,
        source_id="message-reviewer-excluded",
    )
    item = MessageReviewItem(parsed, raw_text=raw)
    item.status = STATUS_EXCLUDED
    item.parsed = replace(
        item.parsed,
        excluded=True,
        exclusion_reason="excluded_by_reviewer",
    )
    fingerprint = fingerprint_message_text(
        raw, source_id=item.source_id, source_path="fixture"
    )
    aggregator = Aggregator(tmp_path / "records.db")
    try:
        dummy = SimpleNamespace(
            _aggregator=aggregator,
            _message_fingerprints={item.source_id: fingerprint},
            _refresh_import_workflow_views=lambda: None,
        )
        MainWindow._persist_message_review_exclusions(dummy, [item])

        assert get_message_rescan_status(aggregator.conn, fingerprint) == "excluded"
        changed = fingerprint_message_text(
            raw + "\nchanged",
            source_id=item.source_id,
            source_path="fixture",
        )
        assert (
            get_message_rescan_status(aggregator.conn, changed)
            == "changed_review_needed"
        )
    finally:
        aggregator.close()


def test_date_missing_keeps_message_workflow_partial(tmp_path: Path) -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    item = MessageReviewItem(
        parse_message(raw, tracked_teams=[], source_id="message-date-needed"),
        raw_text=raw,
    )
    aggregator = Aggregator(tmp_path / "records.db")
    try:
        start_import_workflow(aggregator.conn, WORKFLOW_NEWS_MESSAGES)
        MainWindow._on_message_review_saved(_dummy(aggregator, item), [])
        state = load_import_workflow_state(
            aggregator.conn, WORKFLOW_NEWS_MESSAGES
        )
        assert state.outcome == OUTCOME_PARTIAL_SUCCESS
        assert state.unresolved["date_missing"] == 1
    finally:
        aggregator.close()


def test_all_explicitly_excluded_messages_complete_without_records(
    tmp_path: Path,
) -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    item = MessageReviewItem(
        parse_message(
            raw,
            tracked_teams=[],
            message_date=date(2026, 5, 1),
            source_id="message-excluded",
        ),
        raw_text=raw,
    )
    item.status = STATUS_EXCLUDED
    aggregator = Aggregator(tmp_path / "records.db")
    try:
        start_import_workflow(aggregator.conn, WORKFLOW_NEWS_MESSAGES)
        MainWindow._on_message_review_saved(_dummy(aggregator, item), [])
        state = load_import_workflow_state(
            aggregator.conn, WORKFLOW_NEWS_MESSAGES
        )
        assert state.outcome == OUTCOME_COMPLETED
        assert state.totals["excluded"] == 1
        assert not any(state.unresolved.values())
    finally:
        aggregator.close()
