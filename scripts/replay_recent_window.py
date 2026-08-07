"""Safely replay the most recent correlated OOTP month into a save database.

This is deliberately a maintenance command, not an import shortcut.  It plans
without writing by default and, when asked to execute, does every mutation in a
SQLite working copy.  The live database is replaced only after the replay has
completed successfully; an online SQLite backup is retained beside it.

Window rule
-----------
``end`` is the later of the latest ``games.date`` row (``is_mlb = 1``) and the
latest message date correlated via ``messages.dat``, **inclusive**. ``start``
is exactly one calendar month before ``end`` -- same day-of-month, clamped to
the shorter month's last day (see ``subtract_calendar_month``) -- also
**inclusive**. The window is therefore the closed interval ``[start, end]``:
a game or message dated exactly on either boundary is replayed.

Streak safety (see ``rebuild_season_streaks`` in ``core.streak.tracker``)
---------------------------------------------------------------------------
``player_streak_state`` stores only each streak's current cumulative value,
not a per-date history, so there is no way to safely rewind it to a
mid-season window boundary and replay forward from there -- doing that in
place would risk double-counting games already folded into the stored value.
This tool does not guess at that: instead it uses the existing, tested
``rebuild_season_streaks`` API, which clears a *whole season's* streak state
and replays every one of that season's games (pre-window games included, all
already unchanged on disk) through ``StreakTracker.process_new_games`` from
scratch. That reproduces every game's contribution deterministically using
only production logic, so the result for the touched season(s) is always
consistent -- never a partial, guessed rebuild.

Execute-mode safety model
--------------------------
An ``--execute`` run never mutates the live database in place. It takes an
online SQLite backup, then replays entirely into a separate working-copy
database; only if that replay finishes with no errors and passes
``PRAGMA integrity_check`` is the live database atomically replaced
(``os.replace``) with the finished copy. Any failure at any point leaves the
live database byte-for-byte untouched, with the pre-run backup kept on disk
next to it for inspection or manual restore.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.message_automation.discovery import discover_messages
from core.milestone.message_automation.parser import parse_message
from core.milestone.message_automation.processed import fingerprint_message_file
from core.milestone.message_automation.processed import ensure_processed_messages_schema
from core.milestone.message_automation.recorder import record_parsed_message_result
from core.milestone.prediction_store import PredictionStore
from core.parser.boxscore_html import GAME_BOX_GLOB, summarize_boxscore_file
from core.stats.aggregator import Aggregator
from core.stats.models import BoxscoreFileSnapshot
from core.stats.team_filter import expand_tracked_teams
from core.streak.tracker import rebuild_season_streaks


@dataclass(frozen=True)
class RecentReplayConfig:
    settings_path: Path
    db_path: Path
    save_path: Path
    boxscore_dir: Path
    messages_dir: Path
    milestones_path: Path
    season: int
    tracked_teams: list[str]
    custom_teams: dict[str, str]
    mlb_only: bool
    season_games_total: int
    execute: bool = False


class ReplayPathError(ValueError):
    """An explicitly supplied path (--db/--settings/--save-path) failed validation."""


def _read_settings_dict(settings_path: Path) -> dict[str, Any]:
    """Read settings.json as plain data.

    Deliberately does not use ``SettingsManager.load()``: that call chain
    (``ensure_derived_paths`` -> ``migrate_legacy_shared_db``) creates
    directories and can copy or initialize a *different* per-save
    ``records.db`` under the app's user-data directory purely as a side
    effect of loading settings -- before ``--execute`` and completely
    independent of the ``--db`` path this tool was explicitly given. That is
    exactly the kind of implicit mutation this tool must never perform.
    """
    if not settings_path.is_file():
        raise ReplayPathError(f"Settings file not found: {settings_path}")
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayPathError(f"Could not read settings file {settings_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ReplayPathError(f"Settings file must contain a JSON object: {settings_path}")
    return raw


def subtract_calendar_month(value: date) -> date:
    """Return the same day in the preceding month, clamped where necessary."""
    import calendar
    year, month = (value.year - 1, 12) if value.month == 1 else (value.year, value.month - 1)
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def online_backup(source: Path, destination: Path) -> None:
    """Create a consistent backup without assuming WAL sidecar files are idle.

    ``with sqlite3.connect(...) as conn`` only wraps the transaction (commit
    on success / rollback on error) -- it does not close the connection.
    Leaving the backup connection open holds a file handle that later blocks
    unlinking or replacing that same file on Windows, so both connections are
    explicitly closed here regardless of outcome.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dest:
        src.backup(dest)


def verify_backup(backup_path: Path) -> bool:
    """Confirm a backup file is a structurally sound, openable save database."""
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        return False
    try:
        with closing(sqlite3.connect(backup_path)) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            has_games_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='games'"
            ).fetchone()
    except sqlite3.DatabaseError:
        return False
    return bool(integrity and integrity[0] == "ok" and has_games_table)


def _message_dates(messages_dir: Path) -> list[tuple[Path, date]]:
    scan = discover_messages(messages_dir)
    return [(item.path, item.message_date) for item in scan.messages if item.message_date is not None]


def determine_window(db_path: Path, messages_dir: Path) -> tuple[date, date]:
    """Return inclusive [start, end] from correlated news and imported MLB games."""
    candidates = [when for _, when in _message_dates(messages_dir)]
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT MAX(date) FROM games WHERE is_mlb = 1").fetchone()
    if row and row[0]:
        candidates.append(date.fromisoformat(str(row[0])[:10]))
    if not candidates:
        raise ValueError("Cannot determine replay window: no correlated message date or MLB game date.")
    end = max(candidates)
    return subtract_calendar_month(end), end


def _window_boxscores(config: RecentReplayConfig, start: date, end: date) -> tuple[list[Path], list[dict[str, str]]]:
    selected: list[tuple[date, Path]] = []
    errors: list[dict[str, str]] = []
    if not config.boxscore_dir.is_dir():
        return [], [{"source": str(config.boxscore_dir), "error": "boxscore directory missing"}]
    for path in sorted(config.boxscore_dir.glob(GAME_BOX_GLOB)):
        try:
            summary = summarize_boxscore_file(path)
            if summary is None or not summary.date:
                continue
            game_date = date.fromisoformat(summary.date[:10])
            # Keep every source in the date window.  With mlb_only enabled the
            # production importer intentionally records non-MLB files in its
            # processed ledger, which prevents them becoming noisy "new" files.
            if start <= game_date <= end:
                selected.append((game_date, path))
        except Exception as exc:
            errors.append({"source": path.name, "error": str(exc)})
    return [path for _, path in sorted(selected, key=lambda item: (item[0], item[1].name.lower()))], errors


def _summary(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ("games", "batting_logs", "pitching_logs", "milestone_records", "processed_boxscores", "processed_messages", "milestone_predictions")
    result: dict[str, int] = {}
    for table in tables:
        try:
            result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:
            result[table] = 0
    return result


def _clear_window(aggregator: Aggregator, start: date, end: date) -> tuple[list[int], list[int]]:
    conn = aggregator.conn
    rows = conn.execute(
        "SELECT game_id, season FROM games WHERE is_mlb = 1 AND date BETWEEN ? AND ? ORDER BY date, game_id",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    game_ids = [int(row["game_id"]) for row in rows]
    seasons = sorted({int(row["season"]) for row in rows})
    # The aggregator's internal deletion path is the production provenance rule:
    # it removes generated records while preserving is_manual rows.
    for game_id in game_ids:
        aggregator._delete_game_import_data_in_transaction(game_id)
    # Message-recorded milestones (awards, transfers, injuries, ...) are always
    # persisted with is_manual=1 by MilestoneChecker.record_manual_* -- that
    # column distinguishes "single-row manual-entry code path" from "batch
    # boxscore achievement path", not "was a human at the keyboard". The
    # `source` column is what actually separates a true hand-entered record
    # (source='manual') from one this tool is allowed to clear and re-derive
    # (source='message_auto'), so is_manual must not gate this delete.
    conn.execute(
        "DELETE FROM milestone_records WHERE source = 'message_auto' AND achieved_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    )
    return game_ids, seasons


def _clear_window_source_state(conn: sqlite3.Connection, sources: list[Path], messages_dir: Path, start: date, end: date) -> list[str]:
    """Forget only reprocessed source fingerprints/ledgers, never manual data."""
    filenames = [path.name for path in sources]
    if filenames:
        conn.execute(f"DELETE FROM processed_boxscores WHERE filename IN ({','.join('?' * len(filenames))})", filenames)
    ensure_processed_messages_schema(conn)
    source_ids = [path.stem for path, when in _message_dates(messages_dir) if start <= when <= end]
    if source_ids:
        conn.execute(f"DELETE FROM processed_messages WHERE source_id IN ({','.join('?' * len(source_ids))})", source_ids)
    return source_ids


def _apply_ready_messages(checker: MilestoneChecker, config: RecentReplayConfig, start: date, end: date) -> dict[str, Any]:
    tracked = expand_tracked_teams(config.tracked_teams, config.custom_teams)
    evidence = {"expected": {"mvp": 0, "cy_young": 0}, "created": {"mvp": 0, "cy_young": 0}, "sources": {"mvp": [], "cy_young": []}, "applied": 0, "skipped": 0, "errors": []}
    for path, message_date in _message_dates(config.messages_dir):
        if not start <= message_date <= end:
            continue
        try:
            parsed = parse_message(path.read_text(encoding="utf-8", errors="replace"), tracked_teams=tracked, message_date=message_date, season_hint=config.season, source_id=path.stem)
            category = parsed.category
            label = "mvp" if category == "award_mvp" else "cy_young" if category == "award_cy_young" else None
            # Excluded, ambiguous, errors, and date-required messages are never
            # applied by this unattended command.  A non-empty forms list is the
            # parser's explicit ready-to-record contract.
            if parsed.excluded or not parsed.forms:
                evidence["skipped"] += 1
                continue
            if label:
                evidence["expected"][label] += 1
                evidence["sources"][label].append(path.stem)
            result = record_parsed_message_result(checker, parsed, fingerprint=fingerprint_message_file(path))
            if result.errors:
                evidence["errors"].append({"source": path.stem, "error": "; ".join(result.errors)})
                continue
            evidence["applied"] += 1
            if label:
                evidence["created"][label] += len(result.created_record_ids)
        except Exception as exc:
            evidence["errors"].append({"source": path.stem, "error": str(exc)})
    return evidence


def _unique_sidecar(db_path: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = db_path.with_name(f"{db_path.stem}.{label}.{stamp}{db_path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = db_path.with_name(f"{db_path.stem}.{label}.{stamp}.{counter}{db_path.suffix}")
        counter += 1
    return candidate


def _default_messages_dir(save_path: Path) -> Path:
    """Mirror the GUI's save-layout routing, choosing one deterministic inbox."""
    candidates = (
        save_path / "news" / "html" / "messages",
        save_path / "messages",
        save_path / "news" / "messages",
    )
    existing = [path for path in candidates if path.is_dir()]
    for path in existing:
        if any(path.glob("message*.txt")):
            return path
    return existing[0] if existing else candidates[0]


def _checkpoint_live_for_swap(db_path: Path) -> None:
    """Make a later file replacement safe: no live WAL pages may survive it."""
    with closing(sqlite3.connect(db_path, timeout=1)) as conn:
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if row and (int(row[0]) or int(row[1]) != int(row[2])):
        raise RuntimeError("Live database is busy; WAL checkpoint failed, refusing swap.")
    # A checkpointed WAL may retain a header file on Windows, but with
    # log==checkpointed it contains no uncheckpointed frames to replay.


def _replace_with_retry(source: Path, destination: Path, *, timeout_s: float = 10.0) -> None:
    """Bounded Windows-safe replace for transient OneDrive/AV file handles."""
    deadline = time.monotonic() + max(0.0, timeout_s)
    delay = 0.05
    last_error: OSError | None = None
    while True:
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out replacing live database after {timeout_s:.1f}s: {exc}") from exc
            gc.collect()
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


def run_recent_replay(config: RecentReplayConfig) -> dict[str, Any]:
    start, end = determine_window(config.db_path, config.messages_dir)
    sources, source_errors = _window_boxscores(config, start, end)
    with closing(sqlite3.connect(config.db_path)) as conn:
        before = _summary(conn)
    ready_preview = {"expected": {"mvp": 0, "cy_young": 0}, "created": {"mvp": 0, "cy_young": 0}, "sources": {"mvp": [], "cy_young": []}, "applied": 0, "skipped": 0, "errors": []}
    tracked = expand_tracked_teams(config.tracked_teams, config.custom_teams)
    for path, message_date in _message_dates(config.messages_dir):
        if start <= message_date <= end:
            try:
                parsed = parse_message(path.read_text(encoding="utf-8", errors="replace"), tracked_teams=tracked, message_date=message_date, season_hint=config.season, source_id=path.stem)
                if not parsed.excluded and parsed.forms:
                    key = "mvp" if parsed.category == "award_mvp" else "cy_young" if parsed.category == "award_cy_young" else None
                    if key:
                        ready_preview["expected"][key] += 1
                        ready_preview["sources"][key].append(path.stem)
                    ready_preview["applied"] += 1
                else:
                    ready_preview["skipped"] += 1
            except Exception as exc:
                ready_preview["errors"].append({"source": path.stem, "error": str(exc)})
    window_message_count = sum(1 for _, when in _message_dates(config.messages_dir) if start <= when <= end)
    report: dict[str, Any] = {"dry_run": not config.execute, "window": {"start": start.isoformat(), "end": end.isoformat()}, "db": str(config.db_path), "save": str(config.save_path), "source_boxscores": [path.name for path in sources], "target_counts": {"boxscore_sources": len(sources), "window_messages": window_message_count}, "errors": list(source_errors), "before": before, "after": before, "backup_path": None, "integrity": "not_run", "mvp_cy_evidence": ready_preview}
    if not config.execute:
        return report

    _checkpoint_live_for_swap(config.db_path)
    backup = _unique_sidecar(config.db_path, "recent-replay-backup")
    working = _unique_sidecar(config.db_path, "recent-replay-working")
    finalized = _unique_sidecar(config.db_path, "recent-replay-finalized")
    online_backup(config.db_path, backup)
    if not verify_backup(backup):
        # No mutation may proceed without a verified backup: leave the live
        # DB completely untouched and report the failure instead of guessing.
        backup.unlink(missing_ok=True)
        report["backup_path"] = None
        report["errors"].append({"backup": f"Backup verification failed for {config.db_path}; aborted before any mutation."})
        report["integrity"] = "backup_unverified"
        return report
    online_backup(config.db_path, working)
    report["backup_path"] = str(backup)
    try:
        milestones = load_milestones(config.milestones_path)
        with Aggregator(working) as aggregator:
            conn = aggregator.conn
            conn.execute("BEGIN")
            cleared_games, seasons = _clear_window(aggregator, start, end)
            cleared_messages = _clear_window_source_state(conn, sources, config.messages_dir, start, end)
            snapshots: list[BoxscoreFileSnapshot] = [Aggregator._file_snapshot(path) for path in sources]
            batch = aggregator.import_all_new(config.boxscore_dir, config.season, mlb_only=config.mlb_only, source_snapshot=snapshots, commit=False)
            if batch.errors or batch.deferred_changed:
                raise RuntimeError(f"Boxscore replay failed: errors={len(batch.errors)}, deferred_changed={batch.deferred_changed}")
            imported_rows = conn.execute("SELECT game_id, season FROM games WHERE is_mlb = 1 AND date BETWEEN ? AND ? ORDER BY date, game_id", (start.isoformat(), end.isoformat())).fetchall()
            imported_ids = [int(row["game_id"]) for row in imported_rows]
            imported_ids_by_season: dict[int, list[int]] = {}
            for row in imported_rows:
                imported_ids_by_season.setdefault(int(row["season"]), []).append(int(row["game_id"]))
            seasons = sorted(set(seasons) | set(imported_ids_by_season))
            checker = MilestoneChecker(aggregator, milestones, season_games_total=config.season_games_total, tracked_teams=config.tracked_teams, custom_teams=config.custom_teams)
            recorded = 0
            # A replay window can straddle a season rollover (rare, but the
            # window is date-derived, not season-derived), so achievements are
            # checked per season rather than against one hardcoded season --
            # milestone thresholds and rebuild_season_streaks are both
            # season-scoped.
            for season in seasons:
                season_ids = imported_ids_by_season.get(season, [])
                if season_ids:
                    achievements = checker.check_new_games(season_ids, season)
                    recorded += checker.record_achievements(achievements, commit=False)
                rebuild_season_streaks(aggregator, season, tracked_teams=config.tracked_teams, custom_teams=config.custom_teams, commit=False)
            conn.commit()
            evidence = _apply_ready_messages(checker, config, start, end)
            # PredictionStore currently owns its commits.  This is safe because
            # the live DB is still untouched; any failure discards the copy.
            PredictionStore(aggregator, milestones, season=config.season, season_games_total=config.season_games_total, tracked_teams=config.tracked_teams, custom_teams=config.custom_teams).reseed()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            report.update({"cleared_game_ids": cleared_games, "cleared_message_count": len(cleared_messages), "imported_game_ids": imported_ids, "boxscore_batch": {"imported": batch.imported, "skipped_non_mlb": batch.skipped_non_mlb, "skipped_spring_training": batch.skipped_spring_training}, "achievement_records_created": recorded, "mvp_cy_evidence": evidence, "integrity": integrity})
        if report["integrity"] != "ok" or report["errors"] or report["mvp_cy_evidence"]["errors"]:
            raise RuntimeError("Replay completed with errors; live database was not replaced.")
        # Close/checkpoint the working WAL and materialize a single-file final
        # DB before replacing the live path.  Do not swap a WAL-mode main file.
        online_backup(working, finalized)
        _checkpoint_live_for_swap(config.db_path)
        _replace_with_retry(finalized, config.db_path)
        with closing(sqlite3.connect(config.db_path)) as conn:
            report["after"] = _summary(conn)
        return report
    except Exception as exc:
        report["errors"].append({"replay": str(exc)})
        report["integrity"] = "failed_preserved"
        return report
    finally:
        if working.exists():
            # Windows can retain a just-closed SQLite handle briefly.  A
            # leftover working copy is harmless and, on a failed run, useful
            # for diagnosis; never let cleanup mask the preservation result.
            try:
                working.unlink()
            except OSError:
                pass
        if finalized.exists():
            try:
                finalized.unlink()
            except OSError:
                pass


def _config_from_args(args: argparse.Namespace) -> RecentReplayConfig:
    db_path = Path(args.db)
    save = Path(args.save_path)
    if not db_path.is_file():
        raise ReplayPathError(f"Database not found: {db_path}")
    if not save.is_dir():
        raise ReplayPathError(f"Save path not found or not a directory: {save}")
    settings = _read_settings_dict(Path(args.settings))

    raw_paths = dict(settings.get("paths", {}))
    boxscore_default = Path(str(raw_paths.get("boxscore_dir") or (save / "news" / "html" / "box_scores")))
    messages_dir = Path(args.messages_dir) if args.messages_dir else _default_messages_dir(save)
    milestones_path = (
        Path(args.milestones) if args.milestones else Path(str(settings.get("milestones_path", "data/milestones.csv")))
    )
    tracked_teams = [
        str(team).strip().upper() for team in settings.get("tracked_teams", []) if str(team).strip()
    ]
    custom_teams = {
        str(abbr).strip().upper(): str(name).strip()
        for abbr, name in dict(settings.get("custom_mlb_teams", {})).items()
        if str(abbr).strip() and str(name).strip()
    }
    season = int(args.season) if args.season else int(settings.get("current_season", 2024))
    return RecentReplayConfig(
        Path(args.settings),
        db_path,
        save,
        Path(args.boxscore_dir) if args.boxscore_dir else boxscore_default,
        messages_dir,
        milestones_path,
        season,
        tracked_teams,
        custom_teams,
        bool(settings.get("import_mlb_only", True)),
        int(settings.get("season_games_total", 162)),
        bool(args.execute),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely replay the latest correlated OOTP month.")
    parser.add_argument("--settings", required=True, help="Explicit settings JSON input.")
    parser.add_argument("--db", required=True, help="Explicit live SQLite database input.")
    parser.add_argument("--save-path", required=True, help="Explicit OOTP save input (used only for derived source paths).")
    parser.add_argument("--boxscore-dir"); parser.add_argument("--messages-dir"); parser.add_argument("--milestones"); parser.add_argument("--season", type=int)
    parser.add_argument("--execute", action="store_true", help="Actually replay; without this flag the command is read-only.")
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
    except ReplayPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = run_recent_replay(config)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
