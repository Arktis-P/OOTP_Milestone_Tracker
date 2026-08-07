"""Milestone record source provenance tests."""

from __future__ import annotations

import sqlite3
import json
from datetime import date
from pathlib import Path

import pytest

from core.db.schema import init_database
from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.definitions import (
    MilestoneDefinition,
    MilestoneDefinitions,
    load_milestones,
)
from core.milestone.manual_entry import ManualMilestoneFormData
from core.milestone.message_automation import import_message_file
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "source.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones() -> MilestoneDefinitions:
    return load_milestones(MILESTONES_PATH)


def test_new_schema_has_source_column(aggregator: Aggregator) -> None:
    columns = {
        row["name"]: row
        for row in aggregator.conn.execute("PRAGMA table_info(milestone_records)")
    }

    assert columns["source"]["notnull"] == 1
    assert columns["source"]["dflt_value"] == "'boxscore_auto'"


def test_existing_records_are_backfilled_by_best_available_signal(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE players (
            player_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            short_name TEXT
        );
        CREATE TABLE milestone_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            milestone_key TEXT NOT NULL,
            milestone_label TEXT NOT NULL,
            scope TEXT NOT NULL,
            season INTEGER,
            game_id INTEGER,
            achieved_date TEXT NOT NULL,
            achieved_value REAL NOT NULL,
            is_manual INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO players (player_id, full_name, short_name)
        VALUES (1, 'Player One', 'P. One');
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope,
            season, game_id, achieved_date, achieved_value, is_manual
        ) VALUES
            (1, 'manual_key', 'Manual', 'career', NULL, NULL, '2026-01-01', 1, 1),
            (1, 'season_key', 'Season', 'season_ratio', 2026, NULL, '2026-12-31', 1, 0),
            (1, 'game_key', 'Game', 'game', 2026, 10, '2026-04-01', 1, 0);
        """
    )
    conn.commit()
    conn.close()

    init_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = dict(
            conn.execute(
                "SELECT milestone_key, source FROM milestone_records"
            ).fetchall()
        )
    finally:
        conn.close()

    assert rows == {
        "manual_key": "manual",
        "season_key": "season_final",
        "game_key": "boxscore_auto",
    }


def test_legacy_message_record_is_migrated_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-message.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE players (
            player_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            short_name TEXT
        );
        CREATE TABLE milestone_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            milestone_key TEXT NOT NULL,
            milestone_label TEXT NOT NULL,
            scope TEXT NOT NULL,
            season INTEGER,
            game_id INTEGER,
            achieved_date TEXT NOT NULL,
            achieved_value REAL NOT NULL,
            notes TEXT,
            is_manual INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO players (player_id, full_name, short_name)
        VALUES (1, 'Player One', 'P. One');
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope, season,
            game_id, achieved_date, achieved_value, notes, is_manual
        ) VALUES
            (1, 'message_key', 'Message', 'career', 2026, NULL,
             '2026-05-01', 1, 'source:message1433', 1),
            (1, 'manual_key', 'Manual', 'career', 2026, NULL,
             '2026-05-02', 1, 'entered by user', 1);
        """
    )
    conn.commit()
    conn.close()

    init_database(db_path)
    init_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = dict(
            conn.execute(
                "SELECT milestone_key, source FROM milestone_records"
            ).fetchall()
        )
        report_raw = conn.execute(
            "SELECT value FROM db_meta WHERE key = 'milestone_source_migration_report'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert rows == {"message_key": "message_auto", "manual_key": "manual"}
    report = json.loads(report_raw)
    assert report["message_auto"] == 1
    assert report["manual"] == 1


def test_boxscore_and_season_final_sources_are_recorded(
    aggregator: Aggregator,
) -> None:
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (1, 'A Player', 'A. Player')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (10, '2026-04-01', 2026, 'Away', 'Home', 1, 2, '[]', '[]', 1)
        """
    )
    game_milestone = MilestoneDefinition(
        key="test_game_source",
        label="Game source",
        stat="test",
        threshold=1,
        scope="game",
        category="batting",
    )
    season_milestone = MilestoneDefinition(
        key="test_season_source",
        label="Season source",
        stat="test",
        threshold=1,
        scope="season_ratio",
        category="batting",
    )
    checker = MilestoneChecker(
        aggregator,
        MilestoneDefinitions(batting=[game_milestone, season_milestone], pitching=[]),
    )

    assert checker.record_achievements(
        [
            MilestoneAchievement(
                player_id=1,
                player_name="A. Player",
                milestone=game_milestone,
                current_value=1,
                achieved=True,
                achieved_date="2026-04-01",
                game_id=10,
                season=2026,
            ),
            MilestoneAchievement(
                player_id=1,
                player_name="A. Player",
                milestone=season_milestone,
                current_value=1,
                achieved=True,
                achieved_date="2026-12-31",
                game_id=None,
                season=2026,
            ),
        ]
    ) == 2

    rows = dict(
        aggregator.conn.execute(
            "SELECT milestone_key, source FROM milestone_records"
        ).fetchall()
    )
    assert rows["test_game_source"] == "boxscore_auto"
    assert rows["test_season_source"] == "season_final"


def test_manual_entry_records_manual_source(
    aggregator: Aggregator,
    milestones: MilestoneDefinitions,
) -> None:
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (42, 'Aaron Judge', 'A. Judge')"
    )
    checker = MilestoneChecker(aggregator, milestones)
    record_id = checker.record_manual_milestone(
        ManualMilestoneFormData(
            target="player",
            achieved_date=date(2026, 3, 1),
            player_id=42,
            team=None,
            milestone_key="bat_career_hr_500",
            season=None,
            achieved_value=500.0,
            games_at_achievement=1800,
            opponent_team="",
            opponent_player="",
            description="",
            notes="manual note",
        )
    )

    row = aggregator.conn.execute(
        "SELECT source, is_manual FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["source"] == "manual"
    assert row["is_manual"] == 1


def test_message_import_records_message_auto_source(
    aggregator: Aggregator,
    milestones: MilestoneDefinitions,
) -> None:
    checker = MilestoneChecker(aggregator, milestones)
    result = import_message_file(
        checker,
        ROOT / "tests" / "fixtures" / "messages" / "contract_extension_01.txt",
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )

    assert result.recorded_count == 1
    row = aggregator.conn.execute(
        "SELECT source, is_manual FROM milestone_records"
    ).fetchone()
    assert row["source"] == "message_auto"
    assert row["is_manual"] == 1
