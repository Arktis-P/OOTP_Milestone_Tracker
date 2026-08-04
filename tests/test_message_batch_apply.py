"""Tests for selected/batch apply orchestration in `message_automation.service`.

Exercises `apply_selected_messages` end-to-end against
`discovery.scan_message_directory`, using real fixture message bodies copied
into `messageN.txt`-named files so both the discovery and apply layers are
covered together, the way a real OOTP save directory would be scanned.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions, load_milestones
from core.milestone.message_automation import discovery
from core.milestone.message_automation.service import (
    BatchApplyOutcome,
    CancellationToken,
    apply_selected_messages,
)
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "messages"

TRACKED_TEAMS = ["Seoul Yukies", "Seoul", "SY"]


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "batch_apply.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones() -> MilestoneDefinitions:
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones: MilestoneDefinitions) -> MilestoneChecker:
    return MilestoneChecker(
        aggregator,
        milestones,
        season_games_total=162,
        tracked_teams=TRACKED_TEAMS,
    )


def _seed_messages_dir(tmp_path: Path) -> Path:
    """Copy three real fixtures into messageN.txt files plus a JSON
    messages.dat supplying the exact date the extension-contract fixture
    requires (trade/FA/extension/injury categories have no season-end
    fallback -- field rules S1.4)."""

    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    (messages_dir / "message1.txt").write_text(
        (FIXTURES_DIR / "award_mvp_02.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (messages_dir / "message2.txt").write_text(
        (FIXTURES_DIR / "contract_extension_01.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (messages_dir / "message3.txt").write_text(
        (FIXTURES_DIR / "award_batter_of_month_02.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (messages_dir / "messages.dat").write_text(
        json.dumps({"message2": "2026-05-01"}), encoding="utf-8"
    )
    return messages_dir


def test_apply_selected_messages_processes_all_and_aggregates_counts(
    checker: MilestoneChecker, aggregator: Aggregator, tmp_path: Path
) -> None:
    messages_dir = _seed_messages_dir(tmp_path)
    entries = discovery.scan_message_directory(aggregator.conn, messages_dir)
    assert {entry.status for entry in entries} == {discovery.STATUS_NEW}

    outcome = apply_selected_messages(checker, entries, season_hint=2026)

    assert isinstance(outcome, BatchApplyOutcome)
    assert outcome.total_requested == 3
    assert outcome.processed_count == 3
    assert outcome.not_attempted_count == 0
    assert outcome.cancelled is False
    assert outcome.created_count == 3
    assert outcome.error_count == 0
    assert outcome.excluded_count == 0

    rescanned = discovery.scan_message_directory(aggregator.conn, messages_dir)
    assert {entry.status for entry in rescanned} == {discovery.STATUS_ALREADY_APPLIED}


def test_apply_selected_messages_is_idempotent_on_rerun(
    checker: MilestoneChecker, aggregator: Aggregator, tmp_path: Path
) -> None:
    messages_dir = _seed_messages_dir(tmp_path)
    entries = discovery.scan_message_directory(aggregator.conn, messages_dir)
    apply_selected_messages(checker, entries, season_hint=2026)
    record_count_after_first = aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0]

    rescanned = discovery.scan_message_directory(aggregator.conn, messages_dir)
    second_outcome = apply_selected_messages(checker, rescanned, season_hint=2026)
    record_count_after_second = aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0]

    assert record_count_after_second == record_count_after_first
    assert second_outcome.created_count == 0


def test_apply_selected_messages_honors_cancellation_mid_batch(
    checker: MilestoneChecker, aggregator: Aggregator, tmp_path: Path
) -> None:
    messages_dir = _seed_messages_dir(tmp_path)
    entries = discovery.scan_message_directory(aggregator.conn, messages_dir)
    token = CancellationToken()
    processed_order: list[str] = []

    def on_progress(index: int, total: int, entry) -> None:
        processed_order.append(entry.source_id)
        if index == 1:
            token.cancel()

    outcome = apply_selected_messages(
        checker, entries, season_hint=2026, cancellation=token, on_progress=on_progress
    )

    assert outcome.cancelled is True
    assert outcome.total_requested == 3
    assert outcome.processed_count == 1
    assert outcome.not_attempted_count == 2
    assert processed_order == ["message1"]

    # Only the one processed-before-cancel file left a durable trace.
    rescanned = discovery.scan_message_directory(aggregator.conn, messages_dir)
    by_id = {entry.source_id: entry for entry in rescanned}
    assert by_id["message1"].status == discovery.STATUS_ALREADY_APPLIED
    assert by_id["message2"].status == discovery.STATUS_NEW
    assert by_id["message3"].status == discovery.STATUS_NEW


def test_cancellation_token_before_any_progress_applies_nothing(
    checker: MilestoneChecker, aggregator: Aggregator, tmp_path: Path
) -> None:
    messages_dir = _seed_messages_dir(tmp_path)
    entries = discovery.scan_message_directory(aggregator.conn, messages_dir)
    token = CancellationToken()
    token.cancel()

    outcome = apply_selected_messages(checker, entries, season_hint=2026, cancellation=token)

    assert outcome.cancelled is True
    assert outcome.processed_count == 0
    assert outcome.not_attempted_count == 3
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0] == 0


def test_apply_selected_messages_filtered_by_status_only_applies_new(
    checker: MilestoneChecker, aggregator: Aggregator, tmp_path: Path
) -> None:
    messages_dir = _seed_messages_dir(tmp_path)
    entries = discovery.scan_message_directory(aggregator.conn, messages_dir)
    apply_selected_messages(checker, [entries[0]], season_hint=2026)

    rescanned = discovery.scan_message_directory(aggregator.conn, messages_dir)
    still_new = discovery.filter_scan_entries(rescanned, statuses={discovery.STATUS_NEW})
    assert {entry.source_id for entry in still_new} == {"message2", "message3"}

    outcome = apply_selected_messages(checker, still_new, season_hint=2026)
    assert outcome.total_requested == 2
    assert outcome.created_count == 2
