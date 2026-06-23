"""Test multi-inning BATTING note parsing on import."""

from __future__ import annotations

from pathlib import Path

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


def test_import_multiline_multi_inning_home_runs(tmp_path: Path) -> None:
    if not (SAMPLES_BOX / "game_box_20.html").is_file():
        return

    agg = Aggregator(tmp_path / "multi_hr.db")
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
    data.home_batting_notes = (
        "BATTING\nHome Runs:\n"
        "K. Tucker\n"
        "2 (5, 5th Inning off R. Nelson, 0 on, 0 outs; "
        "7th Inning off B. Pitcher, 0 on, 1 out)\n"
    )
    agg.import_boxscore(data, season=2026)

    tucker_id = next(
        batter.player_id
        for batter in data.home_batting
        if batter.player_name == "K. Tucker"
    )
    row = agg.conn.execute(
        "SELECT home_runs FROM batting_logs WHERE game_id = ? AND player_id = ?",
        (data.meta.game_id, tucker_id),
    ).fetchone()
    assert row is not None
    assert int(row["home_runs"]) == 2

    checker = MilestoneChecker(agg, load_milestones(MILESTONES_PATH), season_games_total=162)
    achievements = checker.check_new_games([data.meta.game_id], season=2026)
    hr2 = [item for item in achievements if item.milestone.key == "bat_game_hr_2"]
    assert any(item.player_id == tucker_id for item in hr2)
    agg.close()
