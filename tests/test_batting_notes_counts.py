"""Per-game event counts from OOTP BATTING notes."""

from __future__ import annotations

from core.parser.batting_notes import get_player_event_counts, parse_team_batting_notes


def test_home_run_paren_is_season_total_not_game_count() -> None:
    notes = (
        "BATTING\nHome Runs:\n"
        "B. Moon (4, 1st Inning off D. May, 2 on, 1 out)\n"
    )
    counts = get_player_event_counts(notes, "B. Moon")
    assert counts.home_runs == 1


def test_home_run_season_total_on_later_inning() -> None:
    notes = (
        "BATTING\nHome Runs:\n"
        "K. Tucker (2, 5th Inning off R. Nelson, 0 on, 0 outs)\n"
    )
    counts = get_player_event_counts(notes, "K. Tucker")
    assert counts.home_runs == 1


def test_home_run_outside_count_is_game_total() -> None:
    notes = (
        "BATTING\nHome Runs:\n"
        "R. Grichuk 2 (5, 6th Inning off P. Blackburn, 1 on, 1 out)\n"
    )
    counts = get_player_event_counts(notes, "R. Grichuk")
    assert counts.home_runs == 2


def test_home_run_two_lines_sum_to_game_total() -> None:
    notes = (
        "BATTING\nHome Runs:\n"
        "H. Kim (1, 4th Inning off A. Pitcher, 1 on, 1 out)\n"
        "H. Kim (2, 7th Inning off B. Pitcher, 3 on, 2 outs)\n"
    )
    counts = get_player_event_counts(notes, "H. Kim")
    assert counts.home_runs == 2


def test_home_run_multiline_multi_inning_detail() -> None:
    """OOTP: name on one line, game count + semicolon innings on the next."""
    notes = (
        "BATTING\nHome Runs:\n"
        "H. Ahn\n"
        "2 (21, 1st Inning off E. Rodriguez, 1 on, 0 outs; "
        "6th Inning off T. Clarke, 1 on, 2 outs)\n"
    )
    counts = get_player_event_counts(notes, "H. Ahn")
    assert counts.home_runs == 2


def test_doubles_paren_is_season_total() -> None:
    notes = (
        "BATTING\nDoubles:\n"
        "M. Muncy (1, 4th Inning off R. Nelson, 1 on, 1 out)\n"
    )
    counts = get_player_event_counts(notes, "M. Muncy")
    assert counts.doubles == 1


def test_stolen_bases_outside_count_is_game_total() -> None:
    counts = parse_team_batting_notes("BATTING\nSB:\nJ. Lee 3 (15)\n")
    assert counts["J. Lee"].stolen_bases == 3
