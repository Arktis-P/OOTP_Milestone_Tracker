"""Near-threshold prediction tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.definitions import MilestoneDefinition, load_milestones
from core.milestone.predictor import is_near
from core.milestone.prediction_store import PredictionStore
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


@pytest.fixture
def milestones():
    return load_milestones(ROOT / "data" / "milestones.csv")


def test_near_n_default_five_percent() -> None:
    milestone = MilestoneDefinition(
        key="career_h_3000",
        label="통산 3000안타",
        stat="career_h",
        threshold=3000,
        scope="career",
        category="batting",
    )
    assert milestone.effective_near_n() == 150.0


def test_near_n_explicit() -> None:
    milestone = MilestoneDefinition(
        key="career_hr_500",
        label="통산 500홈런",
        stat="career_hr",
        threshold=500,
        scope="career",
        category="batting",
        near_n=20,
    )
    assert milestone.effective_near_n() == 20.0
    assert is_near(20, milestone) is True
    assert is_near(21, milestone) is False


def test_career_csv_effective_near_n_default(milestones) -> None:
    hr500 = milestones.get_by_key("bat_career_hr_500")
    assert hr500 is not None
    assert hr500.near_n is None
    assert hr500.effective_near_n() == 25.0


def test_list_cached_sets_is_near(tmp_path: Path, milestones) -> None:
    db_path = tmp_path / "near.db"
    with Aggregator(db_path) as agg:
        for name in ("game_box_13.html", "game_box_14.html"):
            data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
            agg.import_boxscore(data, season=2026)
        store = PredictionStore(
            agg,
            milestones,
            season=2026,
            season_games_total=162,
        )
        store.reseed()
        items = store.list_cached()
        assert all(hasattr(item, "is_near") for item in items)
        near_items = [item for item in items if item.is_near]
        for item in near_items:
            assert item.remaining <= item.milestone.effective_near_n()  # type: ignore[union-attr]
