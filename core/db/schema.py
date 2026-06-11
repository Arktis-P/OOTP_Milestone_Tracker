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
    is_cg           INTEGER NOT NULL DEFAULT 0,
    is_sho          INTEGER NOT NULL DEFAULT 0,
    is_no_hitter    INTEGER NOT NULL DEFAULT 0,
    is_perfect_game INTEGER NOT NULL DEFAULT 0,
    UNIQUE(game_id, player_id)
);

CREATE TABLE IF NOT EXISTS db_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS career_batting_init (
    player_id   INTEGER NOT NULL,
    season      INTEGER NOT NULL,
    g           INTEGER NOT NULL DEFAULT 0,
    pa          INTEGER NOT NULL DEFAULT 0,
    ab          INTEGER NOT NULL DEFAULT 0,
    h           INTEGER NOT NULL DEFAULT 0,
    doubles     INTEGER NOT NULL DEFAULT 0,
    triples     INTEGER NOT NULL DEFAULT 0,
    hr          INTEGER NOT NULL DEFAULT 0,
    rbi         INTEGER NOT NULL DEFAULT 0,
    r           INTEGER NOT NULL DEFAULT 0,
    sb          INTEGER NOT NULL DEFAULT 0,
    cs          INTEGER NOT NULL DEFAULT 0,
    bb          INTEGER NOT NULL DEFAULT 0,
    hbp         INTEGER NOT NULL DEFAULT 0,
    k           INTEGER NOT NULL DEFAULT 0,
    sh          INTEGER NOT NULL DEFAULT 0,
    sf          INTEGER NOT NULL DEFAULT 0,
    gdp         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, season)
);

CREATE TABLE IF NOT EXISTS career_pitching_init (
    player_id   INTEGER NOT NULL,
    season      INTEGER NOT NULL,
    g           INTEGER NOT NULL DEFAULT 0,
    gs          INTEGER NOT NULL DEFAULT 0,
    w           INTEGER NOT NULL DEFAULT 0,
    l           INTEGER NOT NULL DEFAULT 0,
    s           INTEGER NOT NULL DEFAULT 0,
    ip_outs     INTEGER NOT NULL DEFAULT 0,
    ha          INTEGER NOT NULL DEFAULT 0,
    r           INTEGER NOT NULL DEFAULT 0,
    er          INTEGER NOT NULL DEFAULT 0,
    bb          INTEGER NOT NULL DEFAULT 0,
    hbp         INTEGER NOT NULL DEFAULT 0,
    k           INTEGER NOT NULL DEFAULT 0,
    hr          INTEGER NOT NULL DEFAULT 0,
    cg          INTEGER NOT NULL DEFAULT 0,
    sho         INTEGER NOT NULL DEFAULT 0,
    wp          INTEGER NOT NULL DEFAULT 0,
    bk          INTEGER NOT NULL DEFAULT 0,
    holds       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, season)
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
    recorded_at     TEXT DEFAULT (datetime('now'))
);
"""

MILESTONE_RECORDS_V2_SQL = """
CREATE TABLE IF NOT EXISTS milestone_records_v2 (
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
    recorded_at     TEXT DEFAULT (datetime('now'))
);
"""


def init_database(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate_pre_schema(conn)
        conn.executescript(SCHEMA_SQL)
        _migrate_post_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_pre_schema(conn: sqlite3.Connection) -> None:
    _ensure_db_meta(conn)
    _migrate_players_table(conn)
    _migrate_legacy_log_tables(conn)


def _migrate_post_schema(conn: sqlite3.Connection) -> None:
    _ensure_db_meta(conn)
    _migrate_init_schema_v2(conn)
    _ensure_pitching_special_columns(conn)
    _migrate_milestone_records(conn)
    _ensure_milestone_predictions(conn)


def _ensure_db_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS db_meta (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        )
        """
    )
    from core.db.meta import ensure_meta_defaults

    ensure_meta_defaults(conn)


def _migrate_players_table(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "players")
    if not columns or "player_id" in columns:
        return
    if "id" not in columns:
        return
    conn.executescript(
        """
        CREATE TABLE players_v2 (
            player_id       INTEGER PRIMARY KEY,
            full_name       TEXT NOT NULL,
            short_name      TEXT
        );
        INSERT INTO players_v2 (player_id, full_name, short_name)
        SELECT id, name, name FROM players;
        DROP TABLE players;
        ALTER TABLE players_v2 RENAME TO players;
        """
    )


def _migrate_legacy_log_tables(conn: sqlite3.Connection) -> None:
    """Replace pre-Phase-2 empty log tables that use an older column layout."""
    games_cols = _table_columns(conn, "games")
    if games_cols and "away_team" not in games_cols:
        if conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0:
            conn.execute("DROP TABLE games")

    batting_cols = _table_columns(conn, "batting_logs")
    if batting_cols and "game_id" not in batting_cols:
        if conn.execute("SELECT COUNT(*) FROM batting_logs").fetchone()[0] == 0:
            conn.execute("DROP TABLE batting_logs")

    pitching_cols = _table_columns(conn, "pitching_logs")
    if pitching_cols and "ip_outs" not in pitching_cols:
        if conn.execute("SELECT COUNT(*) FROM pitching_logs").fetchone()[0] == 0:
            conn.execute("DROP TABLE pitching_logs")


def _migrate_init_schema_v2(conn: sqlite3.Connection) -> None:
    from core.db.meta import get_meta, set_meta

    version = get_meta(conn, "init_schema_version", "1")
    if version == "2":
        return
    conn.execute("DELETE FROM career_batting_init")
    conn.execute("DELETE FROM career_pitching_init")
    set_meta(conn, "init_season_coverage", "0")
    set_meta(conn, "init_batting_imported_at", "")
    set_meta(conn, "init_pitching_imported_at", "")
    set_meta(conn, "init_last_refreshed_at", "")
    set_meta(conn, "init_schema_version", "2")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_pitching_special_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "pitching_logs")
    for name, ddl in (
        ("is_cg", "INTEGER NOT NULL DEFAULT 0"),
        ("is_sho", "INTEGER NOT NULL DEFAULT 0"),
        ("is_no_hitter", "INTEGER NOT NULL DEFAULT 0"),
        ("is_perfect_game", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE pitching_logs ADD COLUMN {name} {ddl}")


def _migrate_milestone_records(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "milestone_records")
    if not columns:
        return
    if "scope" in columns and "milestone_label" in columns:
        return

    conn.executescript(MILESTONE_RECORDS_V2_SQL)
    old_cols = columns
    select_parts = [
        "id",
        "player_id",
        "milestone_key",
        (
            "milestone_label"
            if "milestone_label" in old_cols
            else "milestone_key AS milestone_label"
        ),
        ("scope" if "scope" in old_cols else "'career' AS scope"),
        "season",
        ("game_id" if "game_id" in old_cols else "NULL AS game_id"),
        "achieved_date",
        "achieved_value",
        ("notes" if "notes" in old_cols else "NULL AS notes"),
        ("recorded_at" if "recorded_at" in old_cols else "datetime('now') AS recorded_at"),
    ]
    conn.execute(
        f"""
        INSERT INTO milestone_records_v2 (
            id, player_id, milestone_key, milestone_label, scope,
            season, game_id, achieved_date, achieved_value, notes, recorded_at
        )
        SELECT {", ".join(select_parts)}
        FROM milestone_records
        """
    )
    conn.execute("DROP TABLE milestone_records")
    conn.execute("ALTER TABLE milestone_records_v2 RENAME TO milestone_records")


def _ensure_milestone_predictions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS milestone_predictions (
            player_id       INTEGER NOT NULL,
            milestone_key   TEXT NOT NULL,
            season          INTEGER NOT NULL,
            player_name     TEXT NOT NULL,
            milestone_label TEXT NOT NULL,
            grade           TEXT NOT NULL,
            current_value   REAL NOT NULL,
            threshold       REAL NOT NULL,
            remaining       REAL NOT NULL,
            progress_pct    REAL NOT NULL,
            season_note     TEXT NOT NULL DEFAULT '',
            updated_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (player_id, milestone_key, season)
        )
        """
    )
