from __future__ import annotations

import sqlite3
from pathlib import Path

from core.db.sqlite_config import configure_sqlite_connection
from core.stats.aggregator import Aggregator
from core.streak.center_model import StreakCenterFilters, load_streak_center


def _active_state(
    aggregator: Aggregator,
    *,
    season: int = 2026,
    player_id: int = 7,
    streak_type: str = "hit_streak",
    current: int = 5,
    outs: int = 0,
    start: str = "2026-04-01",
    last: str = "2026-04-05",
) -> None:
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (?, ?, ?)
        """,
        (player_id, f"Player {player_id}", f"P{player_id}"),
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (game_id, player_id, season, team, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (player_id, player_id, season, "SEA", last),
    )
    aggregator.conn.execute(
        """
        INSERT INTO player_streak_state (
            season, player_id, streak_type, current_value, ip_outs_accum,
            first_success_game_date, last_success_game_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (season, player_id, streak_type, current, outs, start, last),
    )
    aggregator.conn.commit()


def _ended_record(
    aggregator: Aggregator,
    *,
    record_player_id: int,
    season: int = 2026,
    date: str = "2026-05-01",
    value: int = 10,
    team: str = "SEA",
    streak_type: str = "hit_streak",
    event_type: str = "streak_ended",
    description: str = "stored ended streak",
) -> None:
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (?, ?, ?)
        """,
        (record_player_id, f"Full {record_player_id}", f"Short {record_player_id}"),
    )
    aggregator.conn.execute(
        """
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope, season, game_id,
            achieved_date, achieved_value, team, description, streak_type,
            streak_run_id, streak_event_type
        ) VALUES (?, ?, ?, 'streak', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_player_id,
            f"streak_{streak_type}",
            "Stored label",
            season,
            record_player_id,
            date,
            value,
            team,
            description,
            streak_type,
            f"{season}-{record_player_id}-{streak_type}-1",
            event_type,
        ),
    )
    aggregator.conn.commit()


def test_streak_center_isolates_season_and_formats_active(tmp_path: Path) -> None:
    aggregator = Aggregator(tmp_path / "center-season.db")
    try:
        _active_state(aggregator, season=2026, player_id=7, current=6)
        _active_state(aggregator, season=2025, player_id=8, current=30)
        _ended_record(aggregator, record_player_id=7, season=2026)
        _ended_record(aggregator, record_player_id=8, season=2025)

        model = load_streak_center(aggregator, 2026)

        assert [row.player_id for row in model.active] == [7]
        assert model.active[0].display_value == "6"
        assert model.active[0].unit == "games"
        assert [row.player_id for row in model.ended] == [7]
        assert all(row.season == 2026 for row in [*model.active, *model.ended])
    finally:
        aggregator.close()


def test_streak_center_ended_order_and_reason(tmp_path: Path) -> None:
    aggregator = Aggregator(tmp_path / "center-ended.db")
    try:
        _ended_record(
            aggregator,
            record_player_id=1,
            date="2026-05-01",
            description="older stored record",
        )
        _ended_record(
            aggregator,
            record_player_id=2,
            date="2026-05-03",
            description="newer stored record",
        )

        model = load_streak_center(aggregator, 2026)

        assert [row.player_id for row in model.ended] == [2, 1]
        assert model.ended[0].event_reason == "Ended"
        assert model.ended[0].description == "newer stored record"
        assert model.note.endswith("available stored streak records only.")
    finally:
        aggregator.close()


def test_streak_center_unknown_ended_type_uses_raw_value_without_unit(
    tmp_path: Path,
) -> None:
    aggregator = Aggregator(tmp_path / "center-ended-unknown.db")
    try:
        _ended_record(
            aggregator,
            record_player_id=3,
            streak_type="future_streak",
            value=12,
        )

        model = load_streak_center(aggregator, 2026)

        assert len(model.ended) == 1
        assert model.ended[0].streak_type == "future_streak"
        assert model.ended[0].display_value == "12"
        assert model.ended[0].unit == ""
    finally:
        aggregator.close()


def test_streak_center_known_outs_ended_type_formats_as_ip(tmp_path: Path) -> None:
    aggregator = Aggregator(tmp_path / "center-ended-outs.db")
    try:
        _ended_record(
            aggregator,
            record_player_id=4,
            streak_type="scoreless_innings_streak",
            value=47,
        )

        model = load_streak_center(aggregator, 2026)

        assert len(model.ended) == 1
        assert model.ended[0].streak_type == "scoreless_innings_streak"
        assert model.ended[0].display_value == "15.2"
        assert model.ended[0].unit == "IP"
    finally:
        aggregator.close()


def test_streak_center_filters_and_search(tmp_path: Path) -> None:
    aggregator = Aggregator(tmp_path / "center-filter.db")
    try:
        _active_state(aggregator, player_id=10, streak_type="hit_streak")
        _active_state(
            aggregator,
            player_id=11,
            streak_type="scoreless_innings_streak",
            current=0,
            outs=12,
        )
        _ended_record(
            aggregator,
            record_player_id=12,
            team="BOS",
            streak_type="hit_streak",
            description="needle text",
        )

        by_type = load_streak_center(
            aggregator,
            2026,
            filters=StreakCenterFilters(streak_type="scoreless_innings_streak"),
        )
        by_search = load_streak_center(
            aggregator,
            2026,
            filters=StreakCenterFilters(search="needle"),
        )
        by_team = load_streak_center(
            aggregator,
            2026,
            filters=StreakCenterFilters(team="BOS"),
        )

        assert [row.player_id for row in by_type.active] == [11]
        assert by_type.active[0].display_value == "4.0"
        assert [row.player_id for row in by_search.ended] == [12]
        assert by_team.active == []
        assert [row.player_id for row in by_team.ended] == [12]
    finally:
        aggregator.close()


def test_streak_center_excludes_team_records_and_empty(tmp_path: Path) -> None:
    aggregator = Aggregator(tmp_path / "center-team.db")
    try:
        _ended_record(aggregator, record_player_id=0, team="SEA")

        model = load_streak_center(aggregator, 2026)

        assert model.active == []
        assert model.ended == []
        assert model.player_options == []
    finally:
        aggregator.close()


def test_streak_center_old_database_without_ended_columns_is_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
    conn.executescript(
        """
        CREATE TABLE players (
            player_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            short_name TEXT
        );
        CREATE TABLE batting_logs (
            game_id INTEGER,
            player_id INTEGER,
            season INTEGER,
            team TEXT,
            date TEXT
        );
        CREATE TABLE pitching_logs (
            game_id INTEGER,
            player_id INTEGER,
            season INTEGER,
            team TEXT,
            date TEXT
        );
        CREATE TABLE player_streak_state (
            season INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            streak_type TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            ip_outs_accum INTEGER NOT NULL DEFAULT 0,
            first_success_game_date TEXT,
            last_success_game_date TEXT,
            last_success_game_id INTEGER
        );
        CREATE TABLE milestone_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            milestone_key TEXT NOT NULL,
            milestone_label TEXT NOT NULL,
            scope TEXT NOT NULL,
            season INTEGER,
            achieved_date TEXT NOT NULL,
            achieved_value REAL NOT NULL
        );
        """
    )

    class OldAggregator:
        pass

    old = OldAggregator()
    old.conn = conn
    try:
        model = load_streak_center(old, 2026)
        assert model.active == []
        assert model.ended == []
    finally:
        conn.close()
