"""Key-value metadata stored in records.db."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

DEFAULT_META: dict[str, str] = {
    "init_batting_imported_at": "",
    "init_pitching_imported_at": "",
    "init_season_coverage": "0",
    "init_last_refreshed_at": "",
    "tracked_teams": "[]",
    "init_schema_version": "2",
}


def ensure_meta_defaults(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULT_META.items():
        conn.execute(
            "INSERT OR IGNORE INTO db_meta (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM db_meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return str(row[0])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO db_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_init_season_coverage(conn: sqlite3.Connection) -> int:
    raw = get_meta(conn, "init_season_coverage", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def touch_import_meta(conn: sqlite3.Connection, kind: str, season_coverage: int) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if kind == "batting":
        set_meta(conn, "init_batting_imported_at", now)
    else:
        set_meta(conn, "init_pitching_imported_at", now)
    set_meta(conn, "init_season_coverage", str(season_coverage))
    set_meta(conn, "init_last_refreshed_at", now)
