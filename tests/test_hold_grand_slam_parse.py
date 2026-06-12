"""Hold and grand slam box score parsing tests."""

from __future__ import annotations

import re

from core.parser.batting_notes import parse_grand_slam_players, player_has_grand_slam
from core.parser.common import HOLD_RE


def test_hold_re_parses_season_total() -> None:
    match = HOLD_RE.search("L. Jackson H (3)")
    assert match is not None
    assert match.group(1) == "3"


def test_grand_slam_from_batting_notes() -> None:
    notes = """
BATTING
2B: A. Player
Home Runs:
  R. Devers (1, 4th Inning off K. Senga, 3 on, 1 out),
"""
    assert player_has_grand_slam(notes, "R. Devers")
    assert "R. Devers" in parse_grand_slam_players(notes)
    assert not player_has_grand_slam(notes, "A. Player")


def test_grand_slam_requires_three_on() -> None:
    notes = """
BATTING
Home Runs:
  J. Lee (1, 5th Inning off A. Pitcher, 1 on, 1 out),
"""
    assert not player_has_grand_slam(notes, "J. Lee")
