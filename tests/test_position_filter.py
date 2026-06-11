"""Position filter and primary position aggregation."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.position_filter import (
    group_position,
    player_matches_position_group,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


def test_group_position_handles_multi_position() -> None:
    assert group_position("RF, CF") == "외야수"
    assert group_position("2B") == "내야수"
    assert group_position("") == "기타"


def test_player_matches_position_group() -> None:
    outfielder = {
        "primary_position": "CF",
        "is_batter": 1,
        "is_pitcher": 0,
    }
    pitcher_only = {
        "primary_position": "",
        "is_batter": 0,
        "is_pitcher": 1,
    }
    assert player_matches_position_group(outfielder, "외야수") is True
    assert player_matches_position_group(outfielder, "투수") is False
    assert player_matches_position_group(pitcher_only, "투수") is True
    assert player_matches_position_group(outfielder, "전체") is True


@pytest.fixture
def aggregator_with_game(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "pos.db")
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    agg.import_boxscore(data, season=2026)
    return agg


def test_import_stores_position_and_primary(aggregator_with_game: Aggregator) -> None:
    row = aggregator_with_game.conn.execute(
        """
        SELECT position FROM batting_logs
        WHERE player_id = 28987 AND game_id = 13
        """
    ).fetchone()
    assert row is not None
    assert str(row["position"]).strip() != ""

    primary = aggregator_with_game.conn.execute(
        "SELECT primary_position FROM players WHERE player_id = 28987"
    ).fetchone()
    assert primary is not None
    assert str(primary["primary_position"]).strip() != ""
