"""One-time backfill for milestone_records metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.db.meta import get_init_season_coverage
from core.milestone.definitions import MilestoneDefinitions, load_milestones

_DEFAULT_MILESTONES = (
    Path(__file__).resolve().parents[2] / "data" / "milestones.csv"
)

_GAMES_SCOPES = frozenset({"season", "season_ratio", "career", "team_season"})

_RECORD_COLUMNS = (
    "id",
    "player_id",
    "milestone_key",
    "scope",
    "season",
    "game_id",
    "achieved_date",
    "team",
    "games_at_achievement",
)


def backfill_games_at_achievement(
    conn: sqlite3.Connection,
    *,
    milestones: MilestoneDefinitions | None = None,
) -> int:
    """
    Fill games_at_achievement for legacy rows (NULL) using game_id / achieved_date.

    Old UI showed game_id in the 「경기」 column; this derives the games-played
    count at that achievement point for season/career/team_season scopes.
    """
    definitions = milestones or load_milestones(_DEFAULT_MILESTONES)
    max_init = get_init_season_coverage(conn)
    rows = conn.execute(
        """
        SELECT id, player_id, milestone_key, scope, season, game_id,
               achieved_date, team, games_at_achievement
        FROM milestone_records
        WHERE games_at_achievement IS NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        record = _as_mapping(row, _RECORD_COLUMNS)
        scope = str(record.get("scope") or "")
        if scope not in _GAMES_SCOPES:
            continue
        milestone = definitions.get_by_key(str(record["milestone_key"]))
        if milestone is None:
            continue
        games = _games_for_record(conn, record, milestone.category, max_init)
        if games is None:
            continue
        conn.execute(
            """
            UPDATE milestone_records
            SET games_at_achievement = ?
            WHERE id = ?
            """,
            (games, record["id"]),
        )
        updated += 1
    return updated


def _games_for_record(
    conn: sqlite3.Connection,
    record: dict[str, Any],
    category: str,
    max_init_season: int,
) -> int | None:
    scope = str(record.get("scope") or "")
    as_of = _as_of_date(conn, record)

    if scope == "team_season":
        team = (record.get("team") or "").strip()
        season = record.get("season")
        if not team or season is None:
            return None
        return _team_games_through_date(conn, team, int(season), as_of)

    player_id = int(record.get("player_id") or 0)
    if not player_id:
        return None
    season = record.get("season")

    if scope in ("season", "season_ratio"):
        if season is None:
            return None
        if category == "batting":
            return _player_batting_games_through_date(
                conn, player_id, int(season), as_of
            )
        return _player_pitching_games_through_date(
            conn, player_id, int(season), as_of
        )

    if scope == "career":
        if category == "batting":
            return _career_batting_games_through_date(
                conn, player_id, as_of, max_init_season
            )
        return _career_pitching_games_through_date(
            conn, player_id, as_of, max_init_season
        )

    return None


def _as_mapping(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in columns}
    return dict(zip(columns, row, strict=True))


def _cell(row: Any, column: str, *, index: int = 0) -> Any:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[column]
    return row[index]


def _as_of_date(conn: sqlite3.Connection, record: dict[str, Any]) -> str:
    game_id = record.get("game_id")
    if game_id:
        row = conn.execute(
            "SELECT date FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row and _cell(row, "date", index=0):
            return str(_cell(row, "date", index=0))
    return str(record.get("achieved_date") or "")


def _player_batting_games_through_date(
    conn: sqlite3.Connection, player_id: int, season: int, as_of_date: str
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT bl.game_id) AS games
        FROM batting_logs bl
        JOIN games gm ON gm.game_id = bl.game_id AND gm.is_mlb = 1
        WHERE bl.player_id = ? AND bl.season = ?
          AND (? = '' OR gm.date <= ?)
        """,
        (player_id, season, as_of_date, as_of_date),
    ).fetchone()
    return int(_cell(row, "games", index=0) or 0) if row else 0


def _player_pitching_games_through_date(
    conn: sqlite3.Connection, player_id: int, season: int, as_of_date: str
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT pl.game_id) AS games
        FROM pitching_logs pl
        JOIN games gm ON gm.game_id = pl.game_id AND gm.is_mlb = 1
        WHERE pl.player_id = ? AND pl.season = ?
          AND (? = '' OR gm.date <= ?)
        """,
        (player_id, season, as_of_date, as_of_date),
    ).fetchone()
    return int(_cell(row, "games", index=0) or 0) if row else 0


def _career_batting_games_through_date(
    conn: sqlite3.Connection,
    player_id: int,
    as_of_date: str,
    max_init_season: int,
) -> int:
    init_row = conn.execute(
        """
        SELECT COALESCE(SUM(g), 0) AS games
        FROM career_batting_init
        WHERE player_id = ? AND season <= ?
        """,
        (player_id, max_init_season),
    ).fetchone()
    log_row = conn.execute(
        """
        SELECT COUNT(DISTINCT bl.game_id) AS games
        FROM batting_logs bl
        JOIN games gm ON gm.game_id = bl.game_id AND gm.is_mlb = 1
        WHERE bl.player_id = ?
          AND (? = '' OR gm.date <= ?)
        """,
        (player_id, as_of_date, as_of_date),
    ).fetchone()
    return int(_cell(init_row, "games", index=0) or 0) + int(
        _cell(log_row, "games", index=0) or 0
    )


def _career_pitching_games_through_date(
    conn: sqlite3.Connection,
    player_id: int,
    as_of_date: str,
    max_init_season: int,
) -> int:
    init_row = conn.execute(
        """
        SELECT COALESCE(SUM(g), 0) AS games
        FROM career_pitching_init
        WHERE player_id = ? AND season <= ?
        """,
        (player_id, max_init_season),
    ).fetchone()
    log_row = conn.execute(
        """
        SELECT COUNT(DISTINCT pl.game_id) AS games
        FROM pitching_logs pl
        JOIN games gm ON gm.game_id = pl.game_id AND gm.is_mlb = 1
        WHERE pl.player_id = ?
          AND (? = '' OR gm.date <= ?)
        """,
        (player_id, as_of_date, as_of_date),
    ).fetchone()
    return int(_cell(init_row, "games", index=0) or 0) + int(
        _cell(log_row, "games", index=0) or 0
    )


def _team_games_through_date(
    conn: sqlite3.Connection, team: str, season: int, as_of_date: str
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS games
        FROM games
        WHERE season = ? AND is_mlb = 1
          AND (home_team = ? OR away_team = ?)
          AND (? = '' OR date <= ?)
        """,
        (season, team, team, as_of_date, as_of_date),
    ).fetchone()
    return int(_cell(row, "games", index=0) or 0) if row else 0
