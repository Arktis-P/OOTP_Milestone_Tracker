"""Database consistency checks."""

from __future__ import annotations

import sqlite3

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
    return (
        f"통산 집계 경고: {seasons_str}시즌이 초기값과 박스스코어에 "
        f"모두 존재합니다. 통산 수치가 부풀려질 수 있습니다. "
        f"초기값 설정 탭에서 해당 시즌을 제외하고 재임포트하세요."
    )
