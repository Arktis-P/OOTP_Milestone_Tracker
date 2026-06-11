"""Career init vs boxscore season overlap detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.db.validation import format_overlap_warning, validate_no_overlap
from core.stats.aggregator import Aggregator


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "overlap.db")
    yield agg
    agg.close()


def test_no_overlap_when_init_before_logs(aggregator: Aggregator) -> None:
    conn = aggregator.conn
    conn.execute(
        """
        INSERT INTO career_batting_init (
            player_id, season, g, pa, ab, h, doubles, triples, hr, rbi, r,
            sb, cs, bb, hbp, k, sh, sf, gdp
        ) VALUES (1, 2025, 10, 40, 38, 12, 2, 0, 1, 5, 4, 0, 0, 3, 0, 8, 0, 0, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings,
            away_hits, home_hits, away_errors, home_errors,
            ballpark, attendance, game_time, weather,
            player_of_game_id, player_of_game_name, special_notes, is_mlb
        ) VALUES (
            1, '2026-03-27', 2026, 'A', 'B', 0, 0, '[]', '[]', 0, 0, 0, 0,
            '', 0, '', '', NULL, '', '', 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO players (player_id, full_name, short_name) VALUES (1, 'Test', 'T')
        """
    )
    conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, position
        ) VALUES (1, 1, 2026, 'A', '2026-03-27', 4, 'CF')
        """
    )
    conn.commit()
    assert validate_no_overlap(conn) == []


def test_overlap_detected_when_seasons_match(aggregator: Aggregator) -> None:
    conn = aggregator.conn
    conn.execute(
        """
        INSERT INTO career_batting_init (
            player_id, season, g, pa, ab, h, doubles, triples, hr, rbi, r,
            sb, cs, bb, hbp, k, sh, sf, gdp
        ) VALUES (1, 2025, 10, 40, 38, 12, 2, 0, 1, 5, 4, 0, 0, 3, 0, 8, 0, 0, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings,
            away_hits, home_hits, away_errors, home_errors,
            ballpark, attendance, game_time, weather,
            player_of_game_id, player_of_game_name, special_notes, is_mlb
        ) VALUES (
            1, '2025-09-01', 2025, 'A', 'B', 0, 0, '[]', '[]', 0, 0, 0, 0,
            '', 0, '', '', NULL, '', '', 1
        )
        """
    )
    conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (1, 'Test', 'T')"
    )
    conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, position
        ) VALUES (1, 1, 2025, 'A', '2025-09-01', 4, 'CF')
        """
    )
    conn.commit()
    overlaps = validate_no_overlap(conn)
    assert overlaps == [2025]
    assert "2025" in format_overlap_warning(overlaps)
