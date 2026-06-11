"""Team abbreviation resolution for tracked-team filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.definitions import load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    expand_tracked_teams,
    find_unknown_mlb_teams,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


def test_canonical_mlb_has_30_teams() -> None:
    assert len(CANONICAL_MLB_TEAMS) == 30


def test_find_unknown_mlb_teams() -> None:
    unknown = find_unknown_mlb_teams(
        {"ATH": "Athletics", "SF": "San Francisco Giants"},
        CANONICAL_MLB_TEAMS,
    )
    assert "ATH" in unknown
    assert "SF" not in unknown


def test_expand_sf_to_giants() -> None:
    names = expand_tracked_teams(["SF"])
    assert "San Francisco Giants" in names
    assert "SF" in names


@pytest.fixture
def giants_game_db(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "teams.db"
    agg = Aggregator(db_path)
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    agg.import_boxscore(data, season=2026)
    return agg


def test_tracked_sf_matches_boxscore_team_name(giants_game_db: Aggregator) -> None:
    players = giants_game_db.get_tracked_players(["SF"])
    assert len(players) > 0
