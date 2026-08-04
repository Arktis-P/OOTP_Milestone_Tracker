from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from gui.workers.message_scan_worker import MessageScanWorker


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
