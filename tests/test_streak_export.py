"""Streak CSV export tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.stats.aggregator import Aggregator
from core.streak.export import export_streak_csvs
from core.streak.tracker import StreakTracker


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "export.db")
    yield agg
    agg.close()


def _seed_hit_streak_game(aggregator: Aggregator, *, game_id: int, day: int) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (?, ?, 2026, 'A', 'B', 1, 0, '[]', '[]', 1)
        """,
        (game_id, f"2026-03-{day:02d}"),
    )
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (42, 'Test Player', 'T. Player')
        """,
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date,
            ab, r, h, rbi, bb, k, lob,
            home_runs, stolen_bases, hit_by_pitch, is_substitute, is_grand_slam
        ) VALUES (?, 42, 2026, 'Giants', ?, 4, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """,
        (game_id, f"2026-03-{day:02d}"),
    )
    aggregator.conn.commit()


def test_export_streak_csv_bundle(aggregator: Aggregator, tmp_path: Path) -> None:
    for i in range(1, 11):
        _seed_hit_streak_game(aggregator, game_id=i, day=i)
    _seed_hit_streak_game(aggregator, game_id=11, day=11)
    aggregator.conn.execute(
        """
        UPDATE batting_logs SET h = 0
        WHERE game_id = 11 AND player_id = 42
        """
    )
    aggregator.conn.commit()

    tracker = StreakTracker(aggregator)
    tracker.process_new_games(list(range(1, 12)), 2026)

    out_dir = tmp_path / "streak_out"
    result = export_streak_csvs(aggregator, out_dir, 2026)

    assert result.season == 2026
    assert len(result.files) == 7
    expected = {
        "streak_milestone_events.csv",
        "ended_streaks.csv",
        "player_streak_state.csv",
        "parsed_batting_game_logs.csv",
        "parsed_pitching_game_logs.csv",
        "batting_streaks_by_game.csv",
        "pitching_streaks_by_game.csv",
    }
    assert {path.name for path in result.files} == expected

    events_text = (out_dir / "streak_milestone_events.csv").read_text(encoding="utf-8-sig")
    assert "hit_streak" in events_text
    assert "10경기 연속 안타" in events_text

    parsed = (out_dir / "parsed_batting_game_logs.csv").read_text(encoding="utf-8-sig")
    assert "hit_game" in parsed

    snapshots = (out_dir / "batting_streaks_by_game.csv").read_text(encoding="utf-8-sig")
    assert "hit_streak" in snapshots
