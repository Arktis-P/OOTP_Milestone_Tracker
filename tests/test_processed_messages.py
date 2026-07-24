"""Processed message storage and rescan contracts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions, load_milestones
from core.milestone.message_automation import import_message_file
from core.milestone.message_automation.processed import (
    fingerprint_message_file,
    get_message_rescan_status,
    get_processed_message,
)
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "messages" / "contract_extension_01.txt"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "messages.db")
    yield agg
    agg.close()


@pytest.fixture
def checker(aggregator: Aggregator) -> MilestoneChecker:
    return MilestoneChecker(aggregator, load_milestones(MILESTONES_PATH))


def test_processed_message_stores_created_and_duplicate_records(
    checker: MilestoneChecker,
    aggregator: Aggregator,
    tmp_path: Path,
) -> None:
    message_path = tmp_path / "message100.txt"
    message_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    first = import_message_file(
        checker,
        message_path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )
    first_processed = get_processed_message(aggregator.conn, "message100")

    assert first.recorded_count == 1
    assert first.apply_result.created_record_ids == first.record_ids
    assert first_processed is not None
    assert first_processed.status == "applied"
    assert first_processed.created_record_ids == first.record_ids

    second = import_message_file(
        checker,
        message_path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )
    second_processed = get_processed_message(aggregator.conn, "message100")

    assert second.recorded_count == 0
    assert second.apply_result.duplicate_record_ids == first.record_ids
    assert second_processed is not None
    assert second_processed.status == "duplicate"
    assert second_processed.duplicate_record_ids == first.record_ids
    assert aggregator.conn.execute("SELECT COUNT(*) FROM milestone_records").fetchone()[0] == 1


def test_processed_message_rescan_detects_unchanged_applied_and_changed_source(
    checker: MilestoneChecker,
    aggregator: Aggregator,
    tmp_path: Path,
) -> None:
    message_path = tmp_path / "message101.txt"
    message_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    import_message_file(
        checker,
        message_path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )

    assert get_message_rescan_status(
        aggregator.conn,
        fingerprint_message_file(message_path),
    ) == "already_applied"

    message_path.write_text(
        FIXTURE.read_text(encoding="utf-8") + "\nUpdated source text.\n",
        encoding="utf-8",
    )

    assert get_message_rescan_status(
        aggregator.conn,
        fingerprint_message_file(message_path),
    ) == "changed_review_needed"


def test_excluded_message_is_persisted_without_becoming_applied(
    checker: MilestoneChecker,
    aggregator: Aggregator,
) -> None:
    excluded_path = ROOT / "tests" / "fixtures" / "messages" / "trade_deadline_news_01.txt"

    result = import_message_file(
        checker,
        excluded_path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
        tracked_teams=["Seoul Yukies", "Milwaukee Brewers"],
    )
    processed = get_processed_message(aggregator.conn, excluded_path.stem)

    assert result.recorded_count == 0
    assert processed is not None
    assert processed.status == "excluded"
    assert processed.exclusion_reason == "trade_deadline_not_a_transaction"
    assert not processed.is_already_applied
