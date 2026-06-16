"""Save database reset tests."""

from __future__ import annotations

from pathlib import Path

from core.db.reset import reset_save_database, summarize_save_database
from core.stats.aggregator import Aggregator


def test_reset_save_database_clears_imported_data(tmp_path: Path) -> None:
    db_path = tmp_path / "save.db"
    with Aggregator(db_path) as agg:
        agg.upsert_player(1, "A. Player", "A Player")
        agg.conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope,
                achieved_date, achieved_value
            ) VALUES (1, 'test', 'test', 'career', '2026-01-01', 1)
            """
        )
        agg.conn.commit()

    before = summarize_save_database(db_path)
    assert before.milestone_records == 1

    reset_save_database(db_path)

    after = summarize_save_database(db_path)
    assert after.milestone_records == 0
    assert after.games == 0
    assert after.career_batting_init_players == 0

    with Aggregator(db_path) as agg:
        tables = {
            row[0]
            for row in agg.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert "milestone_records" in tables
