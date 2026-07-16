from __future__ import annotations

from core.stats.aggregator import Aggregator
from core.streak.read_model import list_active_streaks


def _state(
    aggregator: Aggregator,
    *,
    player_id: int,
    streak_type: str,
    current: int = 0,
    outs: int = 0,
    start: str | None = "2026-04-01",
    last: str | None = "2026-04-10",
) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO player_streak_state (
            season, player_id, streak_type, current_value, ip_outs_accum,
            first_success_game_date, last_success_game_date
        ) VALUES (2026, ?, ?, ?, ?, ?, ?)
        """,
        (player_id, streak_type, current, outs, start, last),
    )
    aggregator.conn.commit()


def test_active_streak_read_model_formats_outs_and_uses_latest_team(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "active-streak.db")
    try:
        aggregator.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (7, 'Full Name', 'Display Name')
            """
        )
        aggregator.conn.execute(
            """
            INSERT INTO pitching_logs (
                game_id, player_id, season, team, date, ip_outs
            ) VALUES (10, 7, 2026, 'SEA', '2026-04-10', 6)
            """
        )
        _state(
            aggregator,
            player_id=7,
            streak_type="scoreless_innings_streak",
            outs=47,
        )

        rows = list_active_streaks(aggregator, 2026)

        assert len(rows) == 1
        assert rows[0].player_name == "Display Name"
        assert rows[0].team == "SEA"
        assert rows[0].value == 47
        assert rows[0].display_value == "15.2"
        assert rows[0].unit == "IP"
    finally:
        aggregator.close()


def test_active_streak_read_model_unknowns_empty_and_recent_sort(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "active-streak-unknown.db")
    try:
        assert list_active_streaks(aggregator, 2026) == []
        _state(
            aggregator,
            player_id=999,
            streak_type="future_streak",
            current=4,
            start=None,
            last=None,
        )
        _state(
            aggregator,
            player_id=998,
            streak_type="hit_streak",
            current=2,
            last="2026-05-01",
        )

        rows = list_active_streaks(aggregator, 2026, limit=1)

        assert rows[0].player_id == 998
        all_rows = list_active_streaks(aggregator, 2026)
        unknown = next(row for row in all_rows if row.player_id == 999)
        assert unknown.player_name == "Unknown player"
        assert unknown.team == "Unknown team"
        assert unknown.label == "future_streak"
        assert unknown.display_value == "4"
        assert unknown.unit == "games"
    finally:
        aggregator.close()


def test_policy_unit_filtering_happens_before_limit(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "active-streak-units.db")
    try:
        # These two recent rows contain only stale values from the wrong unit.
        _state(
            aggregator,
            player_id=1,
            streak_type="hit_streak",
            current=0,
            outs=99,
            last="2026-06-03",
        )
        _state(
            aggregator,
            player_id=2,
            streak_type="scoreless_innings_streak",
            current=99,
            outs=0,
            last="2026-06-02",
        )
        _state(
            aggregator,
            player_id=3,
            streak_type="hit_streak",
            current=7,
            last="2026-06-01",
        )

        rows = list_active_streaks(aggregator, 2026, limit=1)

        assert [row.player_id for row in rows] == [3]
        assert rows[0].value == 7
    finally:
        aggregator.close()


def test_unknown_policy_prefers_current_then_falls_back_to_outs(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "active-streak-fallback.db")
    try:
        _state(
            aggregator,
            player_id=1,
            streak_type="unknown_both",
            current=3,
            outs=12,
            last="2026-06-02",
        )
        _state(
            aggregator,
            player_id=2,
            streak_type="unknown_outs",
            outs=14,
            last="2026-06-01",
        )

        rows = list_active_streaks(aggregator, 2026)

        assert (rows[0].value, rows[0].display_value, rows[0].unit) == (
            3,
            "3",
            "games",
        )
        assert (rows[1].value, rows[1].display_value, rows[1].unit) == (
            14,
            "14",
            "outs",
        )
    finally:
        aggregator.close()


def test_active_streak_read_model_isolates_season(tmp_path) -> None:
    aggregator = Aggregator(tmp_path / "active-streak-season.db")
    try:
        _state(
            aggregator,
            player_id=1,
            streak_type="hit_streak",
            current=4,
        )
        aggregator.conn.execute(
            """
            INSERT INTO player_streak_state (
                season, player_id, streak_type, current_value,
                first_success_game_date, last_success_game_date
            ) VALUES (2025, 2, 'hit_streak', 20, '2025-04-01', '2025-05-01')
            """
        )
        aggregator.conn.commit()

        rows = list_active_streaks(aggregator, 2026)

        assert [row.player_id for row in rows] == [1]
        assert all(row.season == 2026 for row in rows)
    finally:
        aggregator.close()
