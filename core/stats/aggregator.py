"""SQLite schema and game log aggregation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.stats.models import BattingLog, GameLog, PitchingLog, Player

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    team        TEXT,
    position    TEXT,
    bats        TEXT,
    throws      TEXT
);

CREATE TABLE IF NOT EXISTS batting_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER REFERENCES players(id),
    game_date   TEXT,
    season      INTEGER,
    ab          INTEGER,
    h           INTEGER,
    hr          INTEGER,
    rbi         INTEGER,
    bb          INTEGER,
    so          INTEGER,
    sb          INTEGER,
    r           INTEGER DEFAULT 0,
    doubles     INTEGER DEFAULT 0,
    triples     INTEGER DEFAULT 0,
    UNIQUE(player_id, game_date)
);

CREATE TABLE IF NOT EXISTS pitching_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER REFERENCES players(id),
    game_date   TEXT,
    season      INTEGER,
    ip          REAL,
    h           INTEGER,
    er          INTEGER,
    bb          INTEGER,
    so          INTEGER,
    w           INTEGER,
    l           INTEGER,
    sv          INTEGER,
    UNIQUE(player_id, game_date)
);

CREATE TABLE IF NOT EXISTS milestone_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER REFERENCES players(id),
    milestone_key   TEXT NOT NULL,
    achieved_date   TEXT,
    achieved_value  REAL,
    season          INTEGER,
    notes           TEXT,
    UNIQUE(player_id, milestone_key)
);
"""


class Aggregator:
    """Persists parsed game logs and provides season/career aggregation queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Aggregator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_or_create_player(self, player: Player) -> int:
        row = self._conn.execute(
            "SELECT id FROM players WHERE name = ? AND team = ?",
            (player.name, player.team),
        ).fetchone()
        if row:
            return int(row["id"])

        cursor = self._conn.execute(
            """
            INSERT INTO players (name, team, position, bats, throws)
            VALUES (?, ?, ?, ?, ?)
            """,
            (player.name, player.team, player.position, player.bats, player.throws),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def save_game_log(self, game: GameLog) -> int:
        """Save a game log, skipping duplicate player+date entries."""
        saved = 0
        for batting in game.batting:
            if self._save_batting_log(batting):
                saved += 1
        for pitching in game.pitching:
            if self._save_pitching_log(pitching):
                saved += 1
        return saved

    def _save_batting_log(self, log: BattingLog) -> bool:
        player_id = self.get_or_create_player(
            Player(name=log.player_name, team="", position="")
        )
        try:
            self._conn.execute(
                """
                INSERT INTO batting_logs
                    (player_id, game_date, season, ab, h, hr, rbi, bb, so, sb, r, doubles, triples)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player_id,
                    log.game_date,
                    log.season,
                    log.ab,
                    log.h,
                    log.hr,
                    log.rbi,
                    log.bb,
                    log.so,
                    log.sb,
                    log.r,
                    log.doubles,
                    log.triples,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def _save_pitching_log(self, log: PitchingLog) -> bool:
        player_id = self.get_or_create_player(
            Player(name=log.player_name, team="", position="")
        )
        try:
            self._conn.execute(
                """
                INSERT INTO pitching_logs
                    (player_id, game_date, season, ip, h, er, bb, so, w, l, sv)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player_id,
                    log.game_date,
                    log.season,
                    log.ip,
                    log.h,
                    log.er,
                    log.bb,
                    log.so,
                    log.w,
                    log.l,
                    log.sv,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_season_batting_totals(self, season: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.team,
                   SUM(b.ab) AS ab, SUM(b.h) AS h, SUM(b.hr) AS hr,
                   SUM(b.rbi) AS rbi, SUM(b.bb) AS bb, SUM(b.so) AS so,
                   SUM(b.sb) AS sb
            FROM batting_logs b
            JOIN players p ON p.id = b.player_id
            WHERE b.season = ?
            GROUP BY p.id
            ORDER BY p.name
            """,
            (season,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_career_batting_totals(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.team,
                   SUM(b.ab) AS ab, SUM(b.h) AS h, SUM(b.hr) AS hr,
                   SUM(b.rbi) AS rbi, SUM(b.bb) AS bb, SUM(b.so) AS so,
                   SUM(b.sb) AS sb
            FROM batting_logs b
            JOIN players p ON p.id = b.player_id
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_season_pitching_totals(self, season: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.team,
                   SUM(pl.ip) AS ip, SUM(pl.h) AS h, SUM(pl.er) AS er,
                   SUM(pl.bb) AS bb, SUM(pl.so) AS so,
                   SUM(pl.w) AS w, SUM(pl.l) AS l, SUM(pl.sv) AS sv
            FROM pitching_logs pl
            JOIN players p ON p.id = pl.player_id
            WHERE pl.season = ?
            GROUP BY p.id
            ORDER BY p.name
            """,
            (season,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_career_pitching_totals(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.team,
                   SUM(pl.ip) AS ip, SUM(pl.h) AS h, SUM(pl.er) AS er,
                   SUM(pl.bb) AS bb, SUM(pl.so) AS so,
                   SUM(pl.w) AS w, SUM(pl.l) AS l, SUM(pl.sv) AS sv
            FROM pitching_logs pl
            JOIN players p ON p.id = pl.player_id
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
