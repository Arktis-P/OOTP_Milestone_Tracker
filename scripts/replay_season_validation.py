"""Run a validation-only full-season replay into an isolated SQLite DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.validation.season_replay import (  # noqa: E402
    build_config_from_settings,
    load_message_date_map,
    run_season_replay,
)


def _split_teams(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a season into data/validation/<save-slug>/season-YYYY/records.db "
            "without touching the live save DB or settings import_state."
        )
    )
    parser.add_argument("--settings", help="Settings JSON path. Defaults to app settings.")
    parser.add_argument("--save-path", help="OOTP .lg save path. Defaults to active save.")
    parser.add_argument("--season", type=int, help="Season year. Defaults to settings.current_season.")
    parser.add_argument("--tracked-teams", help="Comma-separated tracked team names/abbreviations.")
    parser.add_argument(
        "--mlb-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Filter boxscores to MLB games. Defaults to settings.import_mlb_only.",
    )
    parser.add_argument("--target-db", help="Explicit validation DB path under a validation directory.")
    parser.add_argument("--validation-root", help="Validation root. Defaults to data/validation.")
    parser.add_argument("--boxscore-dir", help="Override boxscore directory.")
    parser.add_argument("--messages-dir", help="Override OOTP messages directory.")
    parser.add_argument("--milestones", help="Override milestones CSV/JSON path.")
    parser.add_argument(
        "--message-dates",
        help="JSON or CSV map of message filename/stem/source_id to YYYY-MM-DD.",
    )
    parser.add_argument("--reset", action="store_true", help="Delete/recreate only the validation DB.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan inputs and write a report without importing records.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete replay report as JSON.",
    )
    args = parser.parse_args(argv)

    message_dates = load_message_date_map(args.message_dates)
    config = build_config_from_settings(
        settings_path=args.settings,
        save_path=args.save_path,
        season=args.season,
        tracked_teams=_split_teams(args.tracked_teams),
        mlb_only=args.mlb_only,
        target_db=args.target_db,
        validation_root=args.validation_root,
        boxscore_dir=args.boxscore_dir,
        messages_dir=args.messages_dir,
        milestones_path=args.milestones,
        message_dates=message_dates,
        reset=args.reset,
        dry_run=args.dry_run,
    )
    report = run_season_replay(config).to_dict()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Validation DB: {report['target_db']}")
        print(f"Live DB: {report['live_db']}")
        box = report["boxscores"]
        msg = report["messages"]
        db = report["db_summary"]
        print(
            "Boxscores: "
            f"selected={box['season_selected']}/{box['source_total']} "
            f"scanned={box['total_scanned']} "
            f"imported={box['imported']} "
            f"existing={box['skipped_existing']} "
            f"spring={box['skipped_spring_training']} "
            f"errors={len(box['errors']) + len(box.get('source_errors', []))}"
        )
        print(
            "Achievements: "
            f"found={box['achievements_found']} "
            f"recorded={box['achievement_records_created']}"
        )
        print(
            "Messages: "
            f"scanned={msg['total_scanned']} "
            f"imported={msg['imported_messages']} "
            f"records={msg['records_created']} "
            f"skipped={msg['skipped']} "
            f"outside={msg['skipped_outside_season']} "
            f"missing_dates={msg['missing_date_count']} "
            f"errors={len(msg['errors'])}"
        )
        print(
            "DB: "
            f"games={db['games']} "
            f"players={db['players']} "
            f"milestones={db['milestone_records']}"
        )
        print(f"Report: {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
