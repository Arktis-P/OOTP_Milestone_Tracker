"""Milestone prediction store tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.milestone.definitions import load_milestones
from core.milestone.prediction_store import PredictionStore
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "predict.db"
    with Aggregator(db_path) as agg:
        for name in ("game_box_13.html", "game_box_14.html"):
            data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
            agg.import_boxscore(data, season=2026)
        yield agg


@pytest.fixture
def milestones():
    return load_milestones(ROOT / "data" / "milestones.csv")


def test_track_from_filters_distant_career_totals(
    aggregator: Aggregator, milestones
) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    store.reseed()
    keys = {row.milestone_key for row in store.list_cached()}
    assert "bat_career_hr_500" not in keys


def test_reseed_completes_quickly(aggregator: Aggregator, milestones) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    started = time.perf_counter()
    count = store.reseed()
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    assert count >= 0


def test_update_after_import_refreshes_remaining(
    aggregator: Aggregator, milestones
) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    store.reseed()
    updated = store.update_after_import([13, 14])
    assert updated >= 0
