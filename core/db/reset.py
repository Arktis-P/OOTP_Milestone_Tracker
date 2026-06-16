"""Reset per-save tracker database to an empty state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.db.meta import ensure_meta_defaults, get_init_season_coverage
from core.db.schema import init_database
from core.db.sqlite_config import configure_sqlite_connection


@dataclass(frozen=True)
class SaveDataSummary:
    games: int = 0
    players: int = 0
    milestone_records: int = 0
    career_batting_init_players: int = 0
    career_pitching_init_players: int = 0
    milestone_predictions: int = 0
    init_season_coverage: int = 0

    @property
    def has_data(self) -> bool:
        return any(
            (
                self.games,
                self.players,
                self.milestone_records,
                self.career_batting_init_players,
                self.career_pitching_init_players,
                self.milestone_predictions,
                self.init_season_coverage,
            )
        )


def summarize_save_database(db_path: str | Path) -> SaveDataSummary:
    path = Path(db_path)
    if not path.is_file():
        return SaveDataSummary()

    conn = sqlite3.connect(path)
    try:
        configure_sqlite_connection(conn)
        games = _scalar(
            conn,
            """
            SELECT COUNT(*) FROM games
            WHERE is_mlb = 1
            """,
            table="games",
        )
        players = _scalar(
            conn,
            """
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT b.player_id FROM batting_logs b
                JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                UNION
                SELECT pl.player_id FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            )
            """,
            table="batting_logs",
        )
        milestone_records = _scalar(
            conn, "SELECT COUNT(*) FROM milestone_records", table="milestone_records"
        )
        batting_init = _scalar(
            conn,
            "SELECT COUNT(DISTINCT player_id) FROM career_batting_init",
            table="career_batting_init",
        )
        pitching_init = _scalar(
            conn,
            "SELECT COUNT(DISTINCT player_id) FROM career_pitching_init",
            table="career_pitching_init",
        )
        predictions = _scalar(
            conn,
            "SELECT COUNT(*) FROM milestone_predictions",
            table="milestone_predictions",
        )
        coverage = (
            get_init_season_coverage(conn)
            if _table_exists(conn, "db_meta")
            else 0
        )
        return SaveDataSummary(
            games=games,
            players=players,
            milestone_records=milestone_records,
            career_batting_init_players=batting_init,
            career_pitching_init_players=pitching_init,
            milestone_predictions=predictions,
            init_season_coverage=coverage,
        )
    finally:
        conn.close()


def reset_save_database(db_path: str | Path) -> None:
    """Delete and recreate the save database with empty tables."""
    path = Path(db_path)
    if path.is_file():
        path.unlink()
    init_database(path)
    conn = sqlite3.connect(path)
    try:
        configure_sqlite_connection(conn)
        ensure_meta_defaults(conn)
        conn.commit()
    finally:
        conn.close()


def format_save_data_summary(summary: SaveDataSummary) -> str:
    lines = [
        f"MLB 경기: {summary.games:,}건",
        f"기록 선수: {summary.players:,}명",
        f"마일스톤 기록: {summary.milestone_records:,}건",
        f"통산 초기값 (타격): {summary.career_batting_init_players:,}명",
        f"통산 초기값 (투구): {summary.career_pitching_init_players:,}명",
        f"통산 마일스톤 예측: {summary.milestone_predictions:,}건",
    ]
    if summary.init_season_coverage:
        lines.append(f"초기값 시즌 커버리지: {summary.init_season_coverage}시즌까지")
    return "\n".join(lines)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _scalar(conn: sqlite3.Connection, query: str, *, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(query).fetchone()[0])
