"""Shared SQLite connection settings."""

from __future__ import annotations

import sqlite3


def configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    """Enable WAL and wait on lock so GUI + worker threads can share one DB file."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
