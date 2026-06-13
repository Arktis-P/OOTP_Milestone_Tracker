"""Team registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.stats.aggregator import Aggregator
from core.stats.team_filter import is_ootp_mlb_league_row
from core.teams.registry import TeamRegistry


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "teams.db")
    yield agg
    agg.close()


def test_sync_from_export_inserts_and_skips_unchanged(aggregator: Aggregator) -> None:
    rows = [
        {
            "team_id": 25,
            "team_abbr": "SF",
            "team_name": "Giants",
            "league_abbr": "MLB",
            "split_id": 1,
            "league_level_id": 1,
        }
    ]
    registry = TeamRegistry(aggregator.conn)
    first = registry.sync_from_export_rows(rows)
    assert first.inserted == 1
    assert first.updated == 0

    second = registry.sync_from_export_rows(rows)
    assert second.unchanged == 1

    row = aggregator.conn.execute(
        "SELECT team_abbr, team_name, source FROM teams WHERE team_id = 25"
    ).fetchone()
    assert row["team_abbr"] == "SF"
    assert row["source"] == "export"


def test_sync_from_export_updates_on_name_change(aggregator: Aggregator) -> None:
    registry = TeamRegistry(aggregator.conn)
    base = {
        "team_id": 18,
        "team_abbr": "NYY",
        "team_name": "Yankees",
        "league_abbr": "MLB",
        "split_id": 1,
        "league_level_id": 1,
    }
    registry.sync_from_export_rows([base])
    updated_row = dict(base)
    updated_row["team_name"] = "New York Yankees"
    result = registry.sync_from_export_rows([updated_row])
    assert result.updated == 1

    row = aggregator.conn.execute(
        "SELECT team_name FROM teams WHERE team_id = 18"
    ).fetchone()
    assert row["team_name"] == "New York Yankees"


def test_sync_from_boxscore_updates_name(aggregator: Aggregator) -> None:
    registry = TeamRegistry(aggregator.conn)
    registry.upsert(25, team_abbr="SF", team_name="Giants", source="export")

    result = registry.sync_from_boxscore_meta(
        away_team="New York Yankees",
        home_team="San Francisco Giants",
        away_team_id=18,
        home_team_id=25,
    )
    assert result.updated >= 1

    row = aggregator.conn.execute(
        "SELECT team_name, source FROM teams WHERE team_id = 25"
    ).fetchone()
    assert row["team_name"] == "San Francisco Giants"
    assert "boxscore" in row["source"]


def test_resolve_id_by_abbr_and_name(aggregator: Aggregator) -> None:
    registry = TeamRegistry(aggregator.conn)
    registry.upsert(25, team_abbr="SF", team_name="San Francisco Giants", source="export")

    assert registry.resolve_id("SF") == 25
    assert registry.resolve_id("San Francisco Giants") == 25


def test_is_ootp_mlb_league_row_helper() -> None:
    assert is_ootp_mlb_league_row(
        {"split_id": 1, "league_level_id": 1, "league_abbr": "MLB"}
    )
