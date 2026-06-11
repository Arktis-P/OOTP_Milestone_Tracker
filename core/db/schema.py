"""SQLite schema for records.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    game_id         INTEGER PRIMARY KEY,
    date            TEXT NOT NULL,
    season          INTEGER NOT NULL,
    away_team       TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_score      INTEGER NOT NULL,
    home_score      INTEGER NOT NULL,
    away_innings    TEXT NOT NULL,
    home_innings    TEXT NOT NULL,
    away_hits       INTEGER,
    home_hits       INTEGER,
    away_errors     INTEGER,
    home_errors     INTEGER,
    ballpark        TEXT,
    attendance      INTEGER,
    game_time       TEXT,
    weather         TEXT,
    player_of_game_id   INTEGER,
    player_of_game_name TEXT,
    special_notes   TEXT,
    imported_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS players (
    player_id       INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    short_name      TEXT
);

CREATE TABLE IF NOT EXISTS batting_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(game_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    season          INTEGER NOT NULL,
    team            TEXT NOT NULL,
    date            TEXT NOT NULL,
    ab              INTEGER NOT NULL DEFAULT 0,
    r               INTEGER NOT NULL DEFAULT 0,
    h               INTEGER NOT NULL DEFAULT 0,
    rbi             INTEGER NOT NULL DEFAULT 0,
    bb              INTEGER NOT NULL DEFAULT 0,
    k               INTEGER NOT NULL DEFAULT 0,
    lob             INTEGER NOT NULL DEFAULT 0,
    season_avg      REAL,
    season_hr       INTEGER,
    season_rbi      INTEGER,
    doubles         INTEGER NOT NULL DEFAULT 0,
    triples         INTEGER NOT NULL DEFAULT 0,
    home_runs       INTEGER NOT NULL DEFAULT 0,
    stolen_bases    INTEGER NOT NULL DEFAULT 0,
    hit_by_pitch    INTEGER NOT NULL DEFAULT 0,
    gidp            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(game_id, player_id)
);

CREATE TABLE IF NOT EXISTS pitching_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(game_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    season          INTEGER NOT NULL,
    team            TEXT NOT NULL,
    date            TEXT NOT NULL,
    ip_outs         INTEGER NOT NULL,
    h               INTEGER NOT NULL DEFAULT 0,
    r               INTEGER NOT NULL DEFAULT 0,
    er              INTEGER NOT NULL DEFAULT 0,
    bb              INTEGER NOT NULL DEFAULT 0,
    k               INTEGER NOT NULL DEFAULT 0,
    hr              INTEGER NOT NULL DEFAULT 0,
    bf              INTEGER NOT NULL DEFAULT 0,
    pi              INTEGER NOT NULL DEFAULT 0,
    decision        TEXT,
    win             INTEGER NOT NULL DEFAULT 0,
    loss            INTEGER NOT NULL DEFAULT 0,
    save            INTEGER NOT NULL DEFAULT 0,
    season_era      REAL,
    game_score      INTEGER,
    wild_pitch      INTEGER NOT NULL DEFAULT 0,
    hit_batsmen     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(game_id, player_id)
);

CREATE TABLE IF NOT EXISTS milestone_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    milestone_key   TEXT NOT NULL,
    milestone_label TEXT NOT NULL,
    scope           TEXT NOT NULL,
    season          INTEGER,
    game_id         INTEGER,
    achieved_date   TEXT NOT NULL,
    achieved_value  REAL NOT NULL,
    notes           TEXT,
    recorded_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(player_id, milestone_key, season)
);
"""


def init_database(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
