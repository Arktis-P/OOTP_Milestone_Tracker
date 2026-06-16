"""SQLite concurrency settings tests."""

from __future__ import annotations

import threading
from pathlib import Path

from core.stats.aggregator import Aggregator


def test_worker_can_write_while_main_connection_is_open(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    main = Aggregator(db_path)
    errors: list[str] = []

    def worker() -> None:
        try:
            with Aggregator(db_path) as worker_agg:
                worker_agg.upsert_player(999, "W. Worker", "Worker Test")
                worker_agg.conn.commit()
        except Exception as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    row = main.conn.execute(
        "SELECT full_name FROM players WHERE player_id = 999"
    ).fetchone()
    assert row is not None
    assert row["full_name"] == "Worker Test"
    main.close()
