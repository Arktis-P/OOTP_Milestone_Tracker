"""Validation-only full-season replay for box scores and OOTP messages."""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from core.config import paths as app_paths
from core.config.save_db import save_db_slug
from core.config.settings_manager import AppSettings
from core.db.reset import reset_save_database, summarize_save_database
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from core.milestone.message_automation import import_message_file, parse_message
from core.parser.boxscore_html import GAME_BOX_GLOB, summarize_boxscore_file
from core.stats.aggregator import Aggregator
from core.stats.models import BoxscoreFileSnapshot

MESSAGE_GLOB = "message*.txt"
REPORT_NAME = "replay_report.json"
DATE_REQUIRED_REASON = "message_date_required"


@dataclass(frozen=True)
class ReplayConfig:
    save_path: Path
    season: int
    tracked_teams: list[str]
    mlb_only: bool
    target_db: Path
    live_db: Path
    boxscore_dir: Path
    messages_dir: Path
    milestones_path: Path
    game_logs_dir: Path | None = None
    message_dates: Mapping[str, date] = field(default_factory=dict)
    season_games_total: int = 162
    custom_teams: dict[str, str] = field(default_factory=dict)
    reset: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class ReplayReport:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


def validation_db_path(
    save_path: str | Path,
    season: int,
    *,
    validation_root: str | Path | None = None,
) -> Path:
    root = Path(validation_root) if validation_root else app_paths.get_user_data_dir() / "validation"
    return root / save_db_slug(save_path) / f"season-{int(season)}" / "records.db"


def build_config_from_settings(
    *,
    settings_path: str | Path | None = None,
    save_path: str | Path | None = None,
    season: int | None = None,
    tracked_teams: list[str] | None = None,
    mlb_only: bool | None = None,
    target_db: str | Path | None = None,
    validation_root: str | Path | None = None,
    boxscore_dir: str | Path | None = None,
    messages_dir: str | Path | None = None,
    milestones_path: str | Path | None = None,
    message_dates: Mapping[str, date] | None = None,
    reset: bool = False,
    dry_run: bool = False,
) -> ReplayConfig:
    settings = _load_settings_read_only(settings_path)
    raw_save = str(save_path) if save_path is not None else settings.active_save_path
    if not raw_save.strip():
        raise ValueError("No save path was provided and settings.active_save_path is empty.")
    resolved_save = Path(raw_save)

    resolved_season = int(season if season is not None else settings.current_season)
    resolved_target = (
        Path(target_db)
        if target_db is not None
        else validation_db_path(resolved_save, resolved_season, validation_root=validation_root)
    )
    return ReplayConfig(
        save_path=resolved_save,
        season=resolved_season,
        tracked_teams=(
            [team.strip() for team in tracked_teams if team.strip()]
            if tracked_teams is not None
            else list(settings.tracked_teams)
        ),
        mlb_only=bool(settings.import_mlb_only if mlb_only is None else mlb_only),
        target_db=resolved_target,
        live_db=_resolve_settings_db_path(settings),
        boxscore_dir=Path(boxscore_dir or settings.boxscore_dir or resolved_save / "news" / "html" / "box_scores"),
        messages_dir=Path(messages_dir or resolved_save / "messages"),
        milestones_path=Path(
            milestones_path
            if milestones_path is not None
            else _resolve_settings_data_path(settings.milestones_path)
        ),
        game_logs_dir=Path(settings.game_logs_dir) if settings.game_logs_dir else None,
        message_dates=dict(message_dates or {}),
        season_games_total=settings.season_games_total,
        custom_teams=dict(settings.custom_mlb_teams),
        reset=reset,
        dry_run=dry_run,
    )


def load_message_date_map(path: str | Path | None) -> dict[str, date]:
    if path is None:
        return {}
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Message date map not found: {source}")
    if source.suffix.lower() == ".json":
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("JSON message date map must be an object of source_id/date pairs.")
        return {str(key): _parse_iso_date(str(value)) for key, value in raw.items()}
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV message date map must have headers.")
            key_col = _first_present(reader.fieldnames, ("source_id", "source", "filename", "message"))
            date_col = _first_present(reader.fieldnames, ("date", "message_date", "event_date"))
            if key_col is None or date_col is None:
                raise ValueError("CSV message date map requires source_id/filename and date columns.")
            return {
                str(row[key_col]).strip(): _parse_iso_date(str(row[date_col]).strip())
                for row in reader
                if str(row.get(key_col, "")).strip()
            }
    raise ValueError("Message date map must be .json or .csv.")


def run_season_replay(config: ReplayConfig) -> ReplayReport:
    target_db = _canonical(config.target_db)
    live_db = _canonical(config.live_db)
    validation_root = _validation_root_for(target_db)
    _guard_validation_target(target_db, live_db, validation_root, reset=config.reset)

    if config.dry_run:
        report = _dry_run_report(config, target_db, live_db)
        _write_report_atomic(target_db.with_name(REPORT_NAME), report)
        return ReplayReport(report)

    if config.reset:
        reset_save_database(target_db)
    else:
        target_db.parent.mkdir(parents=True, exist_ok=True)

    milestones = load_milestones(config.milestones_path)
    with Aggregator(target_db) as aggregator:
        checker = MilestoneChecker(
            aggregator,
            milestones,
            tracked_teams=list(config.tracked_teams),
            custom_teams=dict(config.custom_teams),
            season_games_total=config.season_games_total,
        )
        boxscore_report = _import_boxscores(aggregator, checker, config)
        messages_report = _import_messages(checker, config)
        db_summary = _db_summary(target_db)

    report = _base_report(config, target_db, live_db)
    report["boxscores"] = boxscore_report
    report["messages"] = messages_report
    report["db_summary"] = db_summary
    report["report_path"] = str(target_db.with_name(REPORT_NAME))
    _write_report_atomic(target_db.with_name(REPORT_NAME), report)
    return ReplayReport(report)


def _import_boxscores(
    aggregator: Aggregator,
    checker: MilestoneChecker,
    config: ReplayConfig,
) -> dict[str, Any]:
    scan = _scan_boxscore_sources(config)
    result = aggregator.import_all_new(
        config.boxscore_dir,
        config.season,
        mlb_only=config.mlb_only,
        source_snapshot=scan["selected_snapshots"],
        commit=False,
    )
    game_ids_for_milestones = sorted(
        set(result.imported_game_ids) | set(result.refreshed_game_ids)
    )
    achievements = []
    recorded = 0
    if game_ids_for_milestones:
        achievements = checker.check_new_games(game_ids_for_milestones, config.season)
        recorded = checker.record_achievements(
            achievements,
            game_logs_dir=str(config.game_logs_dir) if config.game_logs_dir else None,
            commit=False,
        )
    aggregator.conn.commit()
    return {
        "source_total": scan["source_total"],
        "season_selected": len(scan["selected_snapshots"]),
        "skipped_outside_season": scan["skipped_outside_season"],
        "skipped_non_mlb_source": scan["skipped_non_mlb_source"],
        "skipped_invalid_date": scan["skipped_invalid_date"],
        "source_errors": scan["errors"],
        "total_scanned": result.total_scanned,
        "candidates": result.candidates,
        "imported": result.imported,
        "skipped": result.skipped,
        "skipped_existing": result.skipped_existing,
        "skipped_non_mlb": result.skipped_non_mlb,
        "skipped_spring_training": result.skipped_spring_training,
        "deferred_changed": result.deferred_changed,
        "errors": [
            {"game_id": item.game_id, "error": item.error}
            for item in result.errors
        ],
        "imported_game_ids": list(result.imported_game_ids),
        "refreshed_game_ids": list(result.refreshed_game_ids),
        "milestones_checked_games": game_ids_for_milestones,
        "achievements_found": len(achievements),
        "achievement_records_created": recorded,
        "scan_elapsed_s": result.scan_elapsed_s,
        "import_elapsed_s": result.import_elapsed_s,
    }


def _scan_boxscore_sources(config: ReplayConfig) -> dict[str, Any]:
    if not config.boxscore_dir.is_dir():
        return {
            "source_total": 0,
            "selected_snapshots": [],
            "skipped_outside_season": 0,
            "skipped_non_mlb_source": 0,
            "skipped_invalid_date": 0,
            "errors": [],
        }
    files = sorted(config.boxscore_dir.glob(GAME_BOX_GLOB))
    selected: list[BoxscoreFileSnapshot] = []
    skipped_outside = 0
    skipped_non_mlb = 0
    skipped_invalid = 0
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            summary = summarize_boxscore_file(path)
            if summary is None:
                skipped_invalid += 1
                errors.append({"filename": path.name, "error": "Could not summarize boxscore metadata"})
                continue
            if config.mlb_only and not summary.is_mlb:
                skipped_non_mlb += 1
                continue
            if not summary.date:
                skipped_invalid += 1
                errors.append({"filename": path.name, "error": "Could not find game date in box score HTML"})
                continue
            if int(summary.date[:4]) != config.season:
                skipped_outside += 1
                continue
            selected.append(Aggregator._file_snapshot(path))
        except (OSError, ValueError) as exc:
            skipped_invalid += 1
            errors.append({"filename": path.name, "error": str(exc)})
    return {
        "source_total": len(files),
        "selected_snapshots": selected,
        "skipped_outside_season": skipped_outside,
        "skipped_non_mlb_source": skipped_non_mlb,
        "skipped_invalid_date": skipped_invalid,
        "errors": errors,
    }


def _import_messages(checker: MilestoneChecker, config: ReplayConfig) -> dict[str, Any]:
    paths = _message_files(config.messages_dir)
    categories: Counter[str] = Counter()
    exclusions: Counter[str] = Counter()
    missing_dates: list[str] = []
    errors: list[dict[str, str]] = []
    skipped_outside_season: list[str] = []
    imported_messages = 0
    record_count = 0
    excluded_or_not_recorded = 0

    for path in paths:
        message_date = config.message_dates.get(path.name) or config.message_dates.get(path.stem)
        if message_date is not None and message_date.year != config.season:
            skipped_outside_season.append(path.name)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            probe = parse_message(
                text,
                tracked_teams=list(config.tracked_teams),
                message_date=message_date,
                season_hint=None,
                source_id=path.stem,
            )
        except Exception as exc:
            errors.append({"source_id": path.stem, "error": str(exc)})
            continue
        form_seasons = {
            int(getattr(form, "season"))
            for form in probe.forms
            if getattr(form, "season", None) is not None
        }
        if form_seasons and config.season not in form_seasons:
            categories[probe.category] += 1
            skipped_outside_season.append(path.name)
            continue
        try:
            result = import_message_file(
                checker,
                path,
                message_date=message_date,
                season_hint=config.season,
                tracked_teams=list(config.tracked_teams),
            )
        except Exception as exc:
            errors.append({"source_id": path.stem, "error": str(exc)})
            continue

        categories[result.parsed.category] += 1
        if result.parsed.excluded:
            reason = result.parsed.exclusion_reason or "excluded"
            exclusions[reason] += 1
            if reason == DATE_REQUIRED_REASON:
                missing_dates.append(path.name)
        if result.recorded_count:
            imported_messages += 1
            record_count += result.recorded_count
        else:
            excluded_or_not_recorded += 1

    return {
        "total_scanned": len(paths),
        "imported_messages": imported_messages,
        "records_created": record_count,
        "skipped": excluded_or_not_recorded,
        "skipped_outside_season": len(skipped_outside_season),
        "outside_season_sources": skipped_outside_season,
        "errors": errors,
        "categories": dict(sorted(categories.items())),
        "exclusion_reasons": dict(sorted(exclusions.items())),
        "missing_date_count": len(missing_dates),
        "missing_date_sources": missing_dates,
        "date_map_entries": len(config.message_dates),
        "messages_dat": {
            "supported": False,
            "path": str(config.save_path / "messages.dat"),
            "reason": "binary messages.dat parsing is not implemented; provide --message-dates JSON/CSV",
        },
    }


def _dry_run_report(config: ReplayConfig, target_db: Path, live_db: Path) -> dict[str, Any]:
    report = _base_report(config, target_db, live_db)
    boxscore_scan = _scan_boxscore_sources(config)
    categories: Counter[str] = Counter()
    exclusions: Counter[str] = Counter()
    missing_dates: list[str] = []
    errors: list[dict[str, str]] = []
    skipped_outside_season: list[str] = []
    parsed_messages = 0
    parsed_recordable = 0
    parsed_not_recorded = 0
    message_paths = _message_files(config.messages_dir)
    for path in message_paths:
        message_date = config.message_dates.get(path.name) or config.message_dates.get(path.stem)
        if message_date is not None and message_date.year != config.season:
            skipped_outside_season.append(path.name)
            continue
        try:
            parsed = parse_message(
                path.read_text(encoding="utf-8", errors="replace"),
                tracked_teams=list(config.tracked_teams),
                message_date=message_date,
                season_hint=None,
                source_id=path.stem,
            )
        except Exception as exc:
            errors.append({"source_id": path.stem, "error": str(exc)})
            continue
        form_seasons = {
            int(getattr(form, "season"))
            for form in parsed.forms
            if getattr(form, "season", None) is not None
        }
        if form_seasons and config.season not in form_seasons:
            categories[parsed.category] += 1
            skipped_outside_season.append(path.name)
            continue
        parsed_messages += 1
        categories[parsed.category] += 1
        if parsed.excluded:
            reason = parsed.exclusion_reason or "excluded"
            exclusions[reason] += 1
            if reason == DATE_REQUIRED_REASON:
                missing_dates.append(path.name)
            parsed_not_recorded += 1
        elif parsed.forms:
            parsed_recordable += 1
        else:
            parsed_not_recorded += 1

    report["boxscores"] = {
        "source_total": boxscore_scan["source_total"],
        "season_selected": len(boxscore_scan["selected_snapshots"]),
        "skipped_outside_season": boxscore_scan["skipped_outside_season"],
        "skipped_non_mlb_source": boxscore_scan["skipped_non_mlb_source"],
        "skipped_invalid_date": boxscore_scan["skipped_invalid_date"],
        "source_errors": boxscore_scan["errors"],
        "total_scanned": len(boxscore_scan["selected_snapshots"]),
        "candidates": 0,
        "imported": 0,
        "skipped": len(boxscore_scan["selected_snapshots"]),
        "achievements_found": 0,
        "achievement_records_created": 0,
        "errors": [],
        "dry_run": True,
    }
    report["messages"] = {
        "total_scanned": len(message_paths),
        "imported_messages": 0,
        "records_created": 0,
        "parsed_messages": parsed_messages,
        "parsed_recordable": parsed_recordable,
        "skipped": parsed_not_recorded,
        "skipped_outside_season": len(skipped_outside_season),
        "outside_season_sources": skipped_outside_season,
        "errors": errors,
        "categories": dict(sorted(categories.items())),
        "exclusion_reasons": dict(sorted(exclusions.items())),
        "missing_date_count": len(missing_dates),
        "missing_date_sources": missing_dates,
        "date_map_entries": len(config.message_dates),
        "dry_run": True,
        "messages_dat": {
            "supported": False,
            "path": str(config.save_path / "messages.dat"),
            "reason": "binary messages.dat parsing is not implemented; provide --message-dates JSON/CSV",
        },
    }
    report["db_summary"] = _db_summary(target_db)
    report["report_path"] = str(target_db.with_name(REPORT_NAME))
    return report


def _base_report(config: ReplayConfig, target_db: Path, live_db: Path) -> dict[str, Any]:
    return {
        "target_db": str(target_db),
        "live_db": str(live_db),
        "source_dirs": {
            "save": str(config.save_path),
            "boxscores": str(config.boxscore_dir),
            "messages": str(config.messages_dir),
        },
        "season": config.season,
        "tracked_teams": list(config.tracked_teams),
        "mlb_only": config.mlb_only,
        "reset": config.reset,
        "dry_run": config.dry_run,
        "out_of_scope": {
            "streak_processing": "not run by validation replay",
            "prediction_updates": "not run by validation replay",
            "korean_name_notes": "not run by validation replay",
        },
    }


def _db_summary(db_path: Path) -> dict[str, int]:
    summary = summarize_save_database(db_path)
    return {
        "games": summary.games,
        "players": summary.players,
        "milestone_records": summary.milestone_records,
        "career_batting_init_players": summary.career_batting_init_players,
        "career_pitching_init_players": summary.career_pitching_init_players,
        "milestone_predictions": summary.milestone_predictions,
        "init_season_coverage": summary.init_season_coverage,
    }


def _message_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob(MESSAGE_GLOB), key=_message_sort_key)


def _message_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"message(\d+)$", path.stem, re.I)
    return (int(match.group(1)) if match else 2**31, path.name.lower())


def _resolve_settings_db_path(settings: AppSettings) -> Path:
    return _resolve_settings_data_path(settings.db_path)


def _resolve_settings_data_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return _user_data_dir_read_only() / _normalize_data_relative(value)


def _load_settings_read_only(path: str | Path | None) -> AppSettings:
    settings_path = Path(path) if path is not None else _default_settings_path_read_only()
    if not settings_path.is_file():
        return AppSettings()
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    return AppSettings(
        ootp_version=int(raw.get("ootp_version", 25)),
        current_season=int(raw.get("current_season", 2024)),
        ootp_save_root=str(raw.get("ootp_save_root", "")),
        active_save=str(raw.get("active_save", "")),
        active_save_path=str(raw.get("active_save_path", "")),
        paths=dict(raw.get("paths", {})),
        db_path=str(raw.get("db_path", "data/records.db")),
        milestones_path=str(raw.get("milestones_path", "data/milestones.csv")),
        import_state=dict(raw.get("import_state", {})),
        initial_stats_dir=str(raw.get("initial_stats_dir", "")),
        tracked_teams=[
            str(team).strip().upper()
            for team in raw.get("tracked_teams", [])
            if str(team).strip()
        ],
        custom_mlb_teams={
            str(abbr).strip().upper(): str(name).strip()
            for abbr, name in raw.get("custom_mlb_teams", {}).items()
            if str(abbr).strip() and str(name).strip()
        },
        import_mlb_only=bool(raw.get("import_mlb_only", True)),
        season_games_total=int(raw.get("season_games_total", 162)),
        language=str(raw.get("language", "ko")),
        language_selected=bool(raw.get("language_selected", False)),
        gemini_api_key=str(raw.get("gemini_api_key", "")),
        gemini_model_preference=str(raw.get("gemini_model_preference", "gemini-3.5-flash")),
        ratio_qualifiers=dict(
            raw.get(
                "ratio_qualifiers",
                {"batting_ab_per_game": 3.1, "pitching_ip_per_game": 1.0},
            )
        ),
    )


def _default_settings_path_read_only() -> Path:
    return _user_data_dir_read_only() / "settings.json"


def _user_data_dir_read_only() -> Path:
    if app_paths.is_frozen():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / app_paths.APP_DIR_NAME
    return app_paths.get_bundle_root() / "data"


def _normalize_data_relative(relative: str) -> str:
    text = relative.replace("\\", "/").strip("/")
    if text.startswith("data/"):
        return text[len("data/") :]
    return text


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid message date {value!r}; expected YYYY-MM-DD.") from exc


def _first_present(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _validation_root_for(target_db: Path) -> Path:
    parts = list(target_db.parts)
    lowered = [part.lower() for part in parts]
    if "validation" not in lowered:
        raise ValueError("Validation DB must be under a validation directory.")
    index = lowered.index("validation")
    return Path(*parts[: index + 1])


def _guard_validation_target(
    target_db: Path,
    live_db: Path,
    validation_root: Path,
    *,
    reset: bool,
) -> None:
    if target_db == live_db:
        raise ValueError(f"Validation DB target equals the live DB: {target_db}")
    if not _is_relative_to(target_db, validation_root):
        raise ValueError(f"Validation DB target is outside validation root: {target_db}")
    if target_db.name.lower() != "records.db":
        raise ValueError("Validation DB filename must be records.db.")
    if reset:
        parent_name = target_db.parent.name.lower()
        if not re.fullmatch(r"season-\d{4}", parent_name):
            raise ValueError("Refusing to reset a DB outside a season-YYYY validation directory.")


def _canonical(path: Path) -> Path:
    return Path(os.path.normcase(str(path.resolve(strict=False))))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_report_atomic(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        if tmp.is_file():
            tmp.unlink()
        raise


def database_table_counts(path: str | Path) -> dict[str, int]:
    db_path = Path(path)
    if not db_path.is_file():
        return {}
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
    finally:
        conn.close()
