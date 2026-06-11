"""CLI end-to-end pipeline verification: reset → init → boxscores → checks."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.db.validation import validate_no_overlap
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter
from scripts import reset_db

CURRENT_SEASON = 2026
SAMPLE_PLAYER_ID = 28987
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


def run() -> int:
    if not SAMPLES_STATS.is_dir() or not SAMPLES_BOX.is_dir():
        print("samples/ 폴더가 필요합니다 (player_stats_txt, boxscore_html).")
        return 1

    db_path = ROOT / "data" / "records.db"
    reset_db.main()

    milestones = load_milestones(ROOT / "data" / "milestones.csv")

    with Aggregator(db_path) as agg:
        importer = InitialImporter(agg)
        batting = importer.import_batting(
            SAMPLES_STATS / "player_batting_stats.txt",
            "first_time",
            current_season=CURRENT_SEASON,
        )
        pitching = importer.import_pitching(
            SAMPLES_STATS / "player_pitching_stats.txt",
            "first_time",
            current_season=CURRENT_SEASON,
        )
        assert batting.inserted > 0, "타격 초기값 임포트 실패"
        assert pitching.inserted > 0, "투구 초기값 임포트 실패"

        result = agg.import_all_new(SAMPLES_BOX, CURRENT_SEASON, mlb_only=True)
        assert result.imported > 0, "박스스코어 임포트 실패"

        overlaps = validate_no_overlap(agg.conn)
        assert not overlaps, f"이중 집계 시즌 발견: {overlaps}"

        career = agg.get_batting_career(SAMPLE_PLAYER_ID)
        assert career is not None and career["career_hr"] > 0, "통산 집계 실패"

        checker = MilestoneChecker(agg, milestones, season_games_total=162)
        if result.imported_game_ids:
            achievements = checker.check_new_games(
                result.imported_game_ids, CURRENT_SEASON
            )
            checker.record_achievements(achievements)

        milestone_count = agg.conn.execute(
            "SELECT COUNT(*) FROM milestone_records"
        ).fetchone()[0]
        assert milestone_count > 0, "마일스톤 기록 없음"

        wbc_games = agg.conn.execute(
            "SELECT COUNT(*) FROM games WHERE is_mlb = 0"
        ).fetchone()[0]
        positioned = agg.conn.execute(
            "SELECT COUNT(*) FROM batting_logs WHERE position != ''"
        ).fetchone()[0]
        print(f"비MLB 경기 수: {wbc_games}")
        print(f"포지션 저장된 타격 로그: {positioned}")
        print(f"마일스톤 기록: {milestone_count}")
        print("E2E 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
