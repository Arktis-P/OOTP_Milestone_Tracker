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


def test_grand_slam_not_inferred_from_rbi_totals() -> None:
    from core.milestone.game_events import is_grand_slam

    assert not is_grand_slam({"is_grand_slam": 0, "home_runs": 1, "rbi": 4})


def test_grand_slam_d_kim_one_on_not_grand_slam() -> None:
    notes = """
BATTING
Home Runs:
  D. Kim (1, 9th Inning off G. Varland, 1 on, 0 outs),
"""
    assert not player_has_grand_slam(notes, "D. Kim")
    assert "D. Kim" not in parse_grand_slam_players(notes)


def test_grand_slam_player_ids_with_duplicate_short_names() -> None:
    from core.parser.batting_notes import grand_slam_player_ids_for_lineup
    from core.stats.models import BatterLine

    notes = """
BATTING
Home Runs:
  H. Kim (1, 4th Inning off A. Pitcher, 1 on, 1 out),
  H. Kim (1, 7th Inning off B. Pitcher, 3 on, 2 outs),
"""
    lineup = [
        BatterLine(
            player_name="H. Kim",
            player_id=101,
            team="Home",
            position="SS",
            is_substitute=False,
            sub_label="",
            ab=4,
            r=1,
            h=2,
            rbi=2,
            bb=0,
            k=0,
            lob=0,
            avg=0.250,
            season_hr=5,
            season_rbi=20,
        ),
        BatterLine(
            player_name="H. Kim",
            player_id=102,
            team="Home",
            position="PH",
            is_substitute=True,
            sub_label="",
            ab=3,
            r=1,
            h=1,
            rbi=4,
            bb=0,
            k=1,
            lob=0,
            avg=0.200,
            season_hr=10,
            season_rbi=30,
        ),
    ]
    assert grand_slam_player_ids_for_lineup(notes, lineup) == {102}
