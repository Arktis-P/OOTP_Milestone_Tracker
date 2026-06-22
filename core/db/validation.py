"""Database consistency checks."""

from __future__ import annotations

import sqlite3

from core.i18n import tr

_MLB_BAT_SEASONS = """
    SELECT DISTINCT b.season FROM batting_logs b
    JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
"""

_MLB_PIT_SEASONS = """
    SELECT DISTINCT pl.season FROM pitching_logs pl
    JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
"""


def validate_no_overlap(conn: sqlite3.Connection) -> list[int]:
    """
    Return seasons present in MLB boxscore logs that are also covered by init data.

    When init includes season N and batting_logs also has season N, career totals
    double-count that season.
    """
    init_max = conn.execute(
        """
        SELECT MAX(max_season) FROM (
            SELECT COALESCE(MAX(season), 0) AS max_season FROM career_batting_init
            UNION ALL
            SELECT COALESCE(MAX(season), 0) FROM career_pitching_init
        )
        """
    ).fetchone()[0]
    init_max = int(init_max or 0)
    if init_max <= 0:
        return []

    rows = conn.execute(
        f"""
        SELECT DISTINCT season FROM (
            {_MLB_BAT_SEASONS}
            UNION
            {_MLB_PIT_SEASONS}
        )
        ORDER BY season
        """
    ).fetchall()
    log_seasons = [int(row[0]) for row in rows]
    return [season for season in log_seasons if season <= init_max]


def format_overlap_warning(overlaps: list[int]) -> str:
    seasons_str = ", ".join(str(season) for season in overlaps)
    return tr(
        "Career stats warning: {seasons} season(s) exist in both initial data and boxscores. "
        "Career totals may be inflated. "
        "Re-import from the Initial Setup tab, excluding those seasons."
    ).format(seasons=seasons_str)
