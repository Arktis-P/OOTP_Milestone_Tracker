from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.milestone.message_automation.processed import (
    fingerprint_message_file,
    get_processed_message,
    upsert_processed_message,
)
from core.stats.aggregator import Aggregator
from gui.workers.message_scan_worker import (
    SCAN_EXCLUDED,
    SCAN_NEW,
    MessageScanWorker,
)


FIXTURES = Path(__file__).parent / "fixtures" / "messages"


def _scan(
    db_path: Path,
    directory: Path,
    *,
    tracked_teams: list[str],
    custom_teams: dict[str, str] | None = None,
):
    completed = []
    errors: list[str] = []
    worker = MessageScanWorker(
        db_path,
        [directory],
        tracked_teams=tracked_teams,
        custom_teams=custom_teams,
    )
    worker.completed.connect(completed.append)
    worker.error.connect(errors.append)
    worker.run()
    assert errors == []
    assert len(completed) == 1
    return completed[0]


def test_scan_worker_correlates_metadata_from_league_root(tmp_path: Path) -> None:
    save_root = tmp_path / "league.lg"
    messages = save_root / "news" / "html" / "messages"
    messages.mkdir(parents=True)
    (messages / "message7.txt").write_text(
        "Subject: Test\nA harmless unsupported message body.", encoding="utf-8"
    )
    (save_root / "messages.dat").write_text(
        json.dumps({"message7": "2026-05-07"}), encoding="utf-8"
    )

    completed = []
    errors: list[str] = []
    worker = MessageScanWorker(tmp_path / "records.db", [messages])
    worker.completed.connect(completed.append)
    worker.error.connect(errors.append)
    worker.run()

    assert errors == []
    assert len(completed) == 1
    assert completed[0].expected_count == 1
    assert completed[0].items[0].message_date == date(2026, 5, 7)


def test_scan_worker_honors_cancel_before_direct_run(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    (messages / "message1.txt").write_text("Subject: Test", encoding="utf-8")
    cancelled: list[str] = []
    completed = []
    worker = MessageScanWorker(tmp_path / "records.db", [messages])
    worker.cancelled.connect(cancelled.append)
    worker.completed.connect(completed.append)

    worker.cancel()
    worker.run()

    assert cancelled
    assert completed == []


def test_scan_worker_expands_custom_team_for_seoul_awards(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    (messages / "message1.txt").write_text(
        (FIXTURES / "award_mvp_02.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (messages / "message2.txt").write_text(
        (FIXTURES / "award_cy_young_03.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    payload = _scan(
        tmp_path / "records.db",
        messages,
        tracked_teams=["SY"],
        custom_teams={"SY": "Seoul Yukies"},
    )

    assert payload.counts[SCAN_NEW] == 2
    assert {item.category for item in payload.items} == {
        "award_mvp",
        "award_cy_young",
    }
    assert all(
        not item.parsed.excluded and item.generated_count == 1
        for item in payload.items
    )


def test_scan_worker_keeps_unrelated_award_excluded_with_custom_team(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    (messages / "message1.txt").write_text(
        (FIXTURES / "award_cy_young_01.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    payload = _scan(
        tmp_path / "records.db",
        messages,
        tracked_teams=["SY"],
        custom_teams={"SY": "Seoul Yukies"},
    )

    assert payload.counts[SCAN_EXCLUDED] == 1
    assert payload.items[0].parsed.exclusion_reason == "tracked_team_not_involved"


def test_scan_worker_reopens_policy_exclusion_after_custom_team_expansion(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    path = messages / "message1.txt"
    path.write_text(
        (FIXTURES / "award_mvp_02.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    db_path = tmp_path / "records.db"

    first = _scan(db_path, messages, tracked_teams=["SY"])
    assert first.counts[SCAN_EXCLUDED] == 1

    second = _scan(
        db_path,
        messages,
        tracked_teams=["SY"],
        custom_teams={"SY": "Seoul Yukies"},
    )
    assert second.counts[SCAN_NEW] == 1
    assert not second.items[0].parsed.excluded

    with Aggregator(db_path) as aggregator:
        processed = get_processed_message(aggregator.conn, "message1")
    assert processed is not None
    assert processed.status == "candidate"


def test_scan_worker_preserves_reviewer_exclusion_after_custom_team_expansion(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    path = messages / "message1.txt"
    path.write_text(
        (FIXTURES / "award_mvp_02.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    db_path = tmp_path / "records.db"

    with Aggregator(db_path) as aggregator:
        upsert_processed_message(
            aggregator.conn,
            fingerprint=fingerprint_message_file(path),
            status="excluded",
            exclusion_reason="excluded_by_reviewer",
        )

    payload = _scan(
        db_path,
        messages,
        tracked_teams=["SY"],
        custom_teams={"SY": "Seoul Yukies"},
    )
    assert payload.counts[SCAN_EXCLUDED] == 1
    assert payload.items[0].status == "excluded"
