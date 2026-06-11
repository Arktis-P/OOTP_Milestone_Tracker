"""One-shot init reimport + verification (Mode 1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config.settings_manager import SettingsManager, resolve_data_path
from core.db.meta import get_init_season_coverage, get_meta, set_meta
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

SAMPLES = ROOT / "samples" / "player_stats_txt"
BOX_SAMPLE = ROOT / "samples" / "boxscore_html" / "game_box_13.html"


def main() -> int:
    settings = SettingsManager().load()
    db_path = resolve_data_path(settings.db_path)
    # Sample rows are 2025; need season < current_season
    current_season = max(settings.current_season, 2026)

    batting_path = SAMPLES / "player_batting_stats.txt"
    pitching_path = SAMPLES / "player_pitching_stats.txt"
    if not batting_path.is_file() or not pitching_path.is_file():
        print("ERROR: sample stats files missing under", SAMPLES)
        return 1

    agg = Aggregator(db_path)
    conn = agg.conn

    print("=== Step 1: Clear init tables ===")
    conn.execute("DELETE FROM career_batting_init")
    conn.execute("DELETE FROM career_pitching_init")
    set_meta(conn, "init_season_coverage", "0")
    set_meta(conn, "init_batting_imported_at", "")
    set_meta(conn, "init_pitching_imported_at", "")
    set_meta(conn, "init_last_refreshed_at", "")
    conn.commit()
    print("  career_batting_init rows:", conn.execute("SELECT COUNT(*) FROM career_batting_init").fetchone()[0])
    print("  career_pitching_init rows:", conn.execute("SELECT COUNT(*) FROM career_pitching_init").fetchone()[0])

    print("\n=== Step 2: Mode 1 import (first_time) ===")
    print(f"  current_season={current_season} (settings={settings.current_season})")
    importer = InitialImporter(agg)
    bat_result, pit_result = importer.import_all(
        batting_path,
        pitching_path,
        "first_time",
        current_season,
    )
    print(f"  batting: inserted={bat_result.inserted if bat_result else 0}, errors={bat_result.errors if bat_result else []}")
    print(f"  pitching: inserted={pit_result.inserted if pit_result else 0}, errors={pit_result.errors if pit_result else []}")
    if (bat_result and bat_result.errors) or (pit_result and pit_result.errors):
        return 1

    coverage = get_init_season_coverage(conn)
    print(f"  init_season_coverage={coverage}")
    print(f"  batting players={conn.execute('SELECT COUNT(DISTINCT player_id) FROM career_batting_init').fetchone()[0]}")
    print(f"  pitching players={conn.execute('SELECT COUNT(DISTINCT player_id) FROM career_pitching_init').fetchone()[0]}")

    print("\n=== Step 3: Verification ===")
    ok = True

    chisholm = conn.execute(
        "SELECT player_id, full_name, short_name FROM players WHERE player_id = ?", (1259,)
    ).fetchone()
    if chisholm:
        print(f"  [OK] players 1259: {chisholm['full_name']} ({chisholm['short_name']})")
    else:
        print("  [FAIL] players 1259 (Jazz Chisholm Jr.) not found")
        ok = False

    joe_rows = conn.execute(
        "SELECT player_id, season, ab, hr FROM career_batting_init WHERE player_id = ? AND season = ?",
        (151, 2025),
    ).fetchall()
    if len(joe_rows) == 1 and joe_rows[0]["ab"] == 70 and joe_rows[0]["hr"] == 5:
        print(f"  [OK] Connor Joe 2025 aggregated: ab={joe_rows[0]['ab']}, hr={joe_rows[0]['hr']}")
    else:
        print(f"  [FAIL] Connor Joe 2025: expected 1 row ab=70 hr=5, got {len(joe_rows)} row(s)")
        for r in joe_rows:
            print(f"         {dict(r)}")
        ok = False

    init_hr = conn.execute(
        "SELECT COALESCE(SUM(hr),0) FROM career_batting_init WHERE player_id = ? AND season <= ?",
        (28987, coverage),
    ).fetchone()[0]
    logs_hr = conn.execute(
        "SELECT COALESCE(SUM(home_runs),0) FROM batting_logs WHERE player_id = ?", (28987,)
    ).fetchone()[0]
    career = agg.get_batting_career(28987)
    career_hr = int(career["career_hr"]) if career else -1
    expected = int(init_hr) + int(logs_hr)
    if career_hr == expected:
        print(f"  [OK] career_hr 28987: init={init_hr} + logs={logs_hr} = {career_hr}")
    else:
        print(f"  [FAIL] career_hr 28987: expected {expected}, got {career_hr}")
        ok = False

    print("\n=== Step 4: Milestone checker (career_hr_500) ===")
    if logs_hr == 0 and BOX_SAMPLE.is_file():
        data = BoxscoreHTMLParser(BOX_SAMPLE).parse()
        result = agg.import_boxscore(data, season=current_season)
        if result.error:
            print("  boxscore import error:", result.error)
            ok = False
        else:
            print(f"  imported boxscore game_id={data.meta.game_id} for milestone trigger")

    game_ids = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT game_id FROM batting_logs WHERE player_id = ?", (28987,)
        ).fetchall()
    ]
    milestones_path = resolve_data_path(settings.milestones_path)
    if not milestones_path.is_file():
        milestones_path = resolve_data_path("data/milestones.csv")
    milestones = load_milestones(milestones_path)
    checker = MilestoneChecker(agg, milestones, season_games_total=settings.season_games_total)
    achievements = checker.check_new_games(game_ids, season=current_season)
    career500 = [a for a in achievements if a.milestone.key == "career_hr_500" and a.player_id == 28987]
    if career500:
        checker.record_achievements(career500)
        print(f"  recorded career_hr_500 for {career500[0].player_name} (value={career500[0].current_value})")
    else:
        print("  no new career_hr_500 achievement from check_new_games")

    ms = conn.execute(
        """
        SELECT player_id, milestone_key, achieved_value, season, game_id
        FROM milestone_records
        WHERE player_id = ? AND milestone_key = 'career_hr_500'
        """,
        (28987,),
    ).fetchone()
    if ms:
        print(f"  [OK] milestone_records: {dict(ms)}")
    else:
        print("  [FAIL] career_hr_500 not in milestone_records")
        ok = False

    agg.close()
    print("\n=== Done ===", "SUCCESS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
