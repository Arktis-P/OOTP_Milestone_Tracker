"""Tests for per-player BATTING note assignment (duplicate short names)."""

from __future__ import annotations

from core.parser.batting_notes import assign_batting_events_to_lineup
from core.stats.models import BatterLine


def _batter(player_id: int, name: str) -> BatterLine:
    return BatterLine(
        player_name=name,
        player_id=player_id,
        team="SY",
        position="2B",
        is_substitute=False,
        sub_label="",
        ab=4,
        r=0,
        h=1,
        rbi=0,
        bb=0,
        k=0,
        lob=0,
        avg=0.250,
        season_hr=0,
        season_rbi=0,
    )


def test_duplicate_short_name_does_not_share_stolen_bases() -> None:
    notes = "BATTING\nSB:\nH. Kim 3 (15)\n"
    batters = [_batter(1, "H. Kim"), _batter(2, "H. Kim")]

    assigned = assign_batting_events_to_lineup(batters, notes)

    assert assigned[1].stolen_bases == 0
    assert assigned[2].stolen_bases == 0


def test_duplicate_short_name_assigns_when_entry_count_matches() -> None:
    notes = "BATTING\nSB:\nH. Kim 3 (15)\nH. Kim 1 (5)\n"
    batters = [_batter(1, "H. Kim"), _batter(2, "H. Kim")]

    assigned = assign_batting_events_to_lineup(batters, notes)

    assert assigned[1].stolen_bases == 3
    assert assigned[2].stolen_bases == 1


def test_unique_name_still_gets_note_counts() -> None:
    notes = "BATTING\nHome Runs:\nA. Hyun-min 2 (2, 3rd Inning off P. Smith, 0 on, 1 out)\n"
    batters = [_batter(10, "A. Hyun-min")]

    assigned = assign_batting_events_to_lineup(batters, notes)

    assert assigned[10].home_runs == 2
