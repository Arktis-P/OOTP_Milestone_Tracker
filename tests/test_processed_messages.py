"""Processed message storage and rescan contracts."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.manual_entry import ManualInjuryFormData, ManualTransferFormData
from core.milestone.message_automation import import_message_file
from core.milestone.message_automation.parser import ParsedMessage
from core.milestone.message_automation.processed import (
    MessageSourceFingerprint,
    ensure_processed_messages_schema,
    fingerprint_message_file,
    get_message_rescan_status,
    get_processed_message,
)
from core.milestone.message_automation.recorder import record_parsed_message_result
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

    fingerprint_before_touch = fingerprint_message_file(message_path)
    touched_mtime = fingerprint_before_touch.source_mtime + 120
    os.utime(message_path, (touched_mtime, touched_mtime))

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


def test_processed_message_schema_evolves_existing_minimal_table(
    aggregator: Aggregator,
) -> None:
    aggregator.conn.execute(
        "CREATE TABLE processed_messages (source_id TEXT PRIMARY KEY)"
    )
    aggregator.conn.execute(
        "INSERT INTO processed_messages (source_id) VALUES ('legacy-message')"
    )
    aggregator.conn.commit()

    ensure_processed_messages_schema(aggregator.conn)
    processed = get_processed_message(aggregator.conn, "legacy-message")

    assert processed is not None
    assert processed.status == "candidate"
    assert processed.created_record_ids == []
    assert processed.errors == []


def test_message_apply_error_rolls_back_records_and_seeded_players(
    checker: MilestoneChecker,
    aggregator: Aggregator,
) -> None:
    parsed = ParsedMessage(
        category="injury",
        title="Atomic failure",
        excluded=False,
        exclusion_reason=None,
        forms=[
            ManualInjuryFormData(
                player_name="Rollback Player (#880001)",
                achieved_date=date(2026, 5, 1),
                injury_label="day-to-day",
                duration="2 weeks",
                team="Seoul",
                season=2026,
                description="",
                notes="first form should roll back",
            ),
            object(),
        ],
        source_id="message-atomic-error",
    )
    fingerprint = MessageSourceFingerprint(
        source_id="message-atomic-error",
        source_path="",
        source_hash="atomic-error",
        source_mtime=1.0,
    )

    result = record_parsed_message_result(checker, parsed, fingerprint=fingerprint)
    processed = get_processed_message(aggregator.conn, "message-atomic-error")

    assert result.errors
    assert result.created_record_ids == []
    assert processed is not None
    assert processed.status == "error"
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records WHERE notes = ?",
        ("first form should roll back",),
    ).fetchone()[0] == 0
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM players WHERE player_id = 880001"
    ).fetchone()[0] == 0


def test_duplicate_detection_does_not_seed_players(
    checker: MilestoneChecker,
    aggregator: Aggregator,
) -> None:
    notes = "duplicate transfer should not seed"
    aggregator.conn.execute(
        """
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope, season,
            achieved_date, achieved_value, notes, source
        ) VALUES (0, 'manual_transfer_trade', 'Trade', 'manual_event', 2026,
                  '2026-05-01', 1.0, ?, 'message_auto')
        """,
        (notes,),
    )
    aggregator.conn.commit()
    parsed = ParsedMessage(
        category="trade",
        title="Duplicate transfer",
        excluded=False,
        exclusion_reason=None,
        forms=[
            ManualTransferFormData(
                achieved_date=date(2026, 5, 1),
                joining_players="Ghost Player (#990001)",
                leaving_players="",
                event_type="trade",
                join_team="Seoul",
                counterpart_team="Busan",
                season=2026,
                description="",
                notes=notes,
            )
        ],
        source_id="message-duplicate-no-seed",
    )

    result = record_parsed_message_result(
        checker,
        parsed,
        fingerprint=MessageSourceFingerprint(
            source_id="message-duplicate-no-seed",
            source_path="",
            source_hash="duplicate-no-seed",
            source_mtime=1.0,
        ),
    )

    assert result.created_record_ids == []
    assert result.duplicate_record_ids
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM players WHERE player_id = 990001"
    ).fetchone()[0] == 0
