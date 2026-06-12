"""Milestone record backfill tests."""

from __future__ import annotations

from pathlib import Path

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.record_backfill import backfill_games_at_achievement
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


def test_backfill_sets_games_from_linked_game(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill.db"
    agg = Aggregator(db_path)
    try:
        InitialImporter(agg).import_batting(
            SAMPLES_STATS / "player_batting_stats.txt",
            "first_time",
            current_season=2026,
        )
        data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
        agg.import_boxscore(data, season=2026)
        checker = MilestoneChecker(agg, load_milestones(MILESTONES_PATH))
        achievements = checker.check_new_games([data.meta.game_id], season=2026)
        career = [a for a in achievements if a.milestone.key == "bat_career_hr_500"]
        assert career
        checker.record_achievements(career)

        agg.conn.execute(
            "UPDATE milestone_records SET games_at_achievement = NULL"
        )
        agg.conn.commit()

        updated = backfill_games_at_achievement(agg.conn)
        assert updated == 1
        row = agg.conn.execute(
            "SELECT games_at_achievement, game_id FROM milestone_records LIMIT 1"
        ).fetchone()
        assert row["games_at_achievement"] is not None
        assert row["games_at_achievement"] > 0
    finally:
        agg.close()


def test_backfill_skips_game_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "game_scope.db"
    agg = Aggregator(db_path)
    try:
        if not (SAMPLES_BOX / "game_box_20.html").is_file():
            return
        data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
        agg.import_boxscore(data, season=2026)
        checker = MilestoneChecker(agg, load_milestones(MILESTONES_PATH))
        achievements = checker.check_new_games([data.meta.game_id], season=2026)
        game_rows = [a for a in achievements if a.milestone.scope == "game"]
        if not game_rows:
            return
        checker.record_achievements(game_rows)
        agg.conn.execute(
            "UPDATE milestone_records SET games_at_achievement = NULL"
        )
        agg.conn.commit()
        updated = backfill_games_at_achievement(agg.conn)
        assert updated == 0
    finally:
        agg.close()
