"""Team milestone stat helpers."""

from __future__ import annotations

import sqlite3
from typing import Any


def check_team_game_batting(
    conn: sqlite3.Connection, game_id: int, team: str
) -> dict[str, bool]:
    starters = conn.execute(
        """
        SELECT h, r, rbi
        FROM batting_logs bl
        JOIN games g ON g.game_id = bl.game_id AND g.is_mlb = 1
        WHERE bl.game_id = ? AND bl.team = ? AND bl.is_substitute = 0
        """,
        (game_id, team),
    ).fetchall()
    all_players = conn.execute(
        """
        SELECT h, rbi
        FROM batting_logs bl
        JOIN games g ON g.game_id = bl.game_id AND g.is_mlb = 1
        WHERE bl.game_id = ? AND bl.team = ?
        """,
        (game_id, team),
    ).fetchall()
    return {
        "starter_all_hit": bool(starters)
        and all(int(row["h"]) > 0 for row in starters),
        "starter_all_rbi": bool(starters)
        and all(int(row["rbi"]) > 0 for row in starters),
        "starter_all_run": bool(starters)
        and all(int(row["r"]) > 0 for row in starters),
        "all_hit": bool(all_players)
        and all(int(row["h"]) > 0 for row in all_players),
        "all_rbi": bool(all_players)
        and all(int(row["rbi"]) > 0 for row in all_players),
    }


def check_team_game_pitching(
    conn: sqlite3.Connection, game_id: int, team: str
) -> dict[str, bool]:
    row = conn.execute(
        """
        SELECT
            MAX(pl.is_no_hitter) AS team_no_hitter,
            MAX(pl.is_perfect_game) AS team_perfect_game
        FROM pitching_logs pl
        JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
        WHERE pl.game_id = ? AND pl.team = ?
        """,
        (game_id, team),
    ).fetchone()
    if not row:
        return {"team_no_hitter": False, "team_perfect_game": False}
    return {
        "team_no_hitter": bool(row["team_no_hitter"]),
        "team_perfect_game": bool(row["team_perfect_game"]),
    }


def get_team_wins(conn: sqlite3.Connection, team: str, season: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS wins FROM games
        WHERE season = ? AND is_mlb = 1
          AND (
              (home_team = ? AND home_score > away_score) OR
              (away_team = ? AND away_score > home_score)
          )
        """,
        (season, team, team),
    ).fetchone()
    return int(row["wins"]) if row else 0


def team_stat_value(
    conn: sqlite3.Connection,
    *,
    scope: str,
    stat: str,
    team: str,
    game_id: int | None,
    season: int | None,
) -> float | None:
    if scope == "team_game" and game_id is not None:
        if stat in {
            "starter_all_hit",
            "starter_all_rbi",
            "starter_all_run",
            "all_hit",
            "all_rbi",
        }:
            batting = check_team_game_batting(conn, game_id, team)
            return 1.0 if batting.get(stat) else 0.0
        if stat in {"team_no_hitter", "team_perfect_game"}:
            pitching = check_team_game_pitching(conn, game_id, team)
            return 1.0 if pitching.get(stat) else 0.0
    if scope == "team_season" and stat == "team_wins" and season is not None:
        return float(get_team_wins(conn, team, season))
    if scope == "team_manual":
        return 1.0
    return None
