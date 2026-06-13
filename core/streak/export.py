"""Export streak data to CSV files for verification and analysis."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.stats.aggregator import Aggregator
from core.stats.ip_utils import outs_to_ip_str
from core.streak.game_log import batting_log_from_row, pitching_log_from_row
from core.streak.policies import load_streak_policies
from core.streak.tracker import StreakTracker

MILESTONE_EVENT_COLUMNS = [
    "player_id",
    "player_name",
    "team",
    "season",
    "game_id",
    "achieved_date",
    "streak_type",
    "streak_label",
    "streak_event_type",
    "milestone_value",
    "milestone_label",
    "streak_run_id",
    "description",
]

STATE_COLUMNS = [
    "season",
    "player_id",
    "player_name",
    "streak_type",
    "streak_label",
    "current_value",
    "ip_outs_accum",
    "run_index",
    "last_success_game_id",
    "last_success_game_date",
    "recorded_milestones",
]

PARSED_BATTING_COLUMNS = [
    "season",
    "game_id",
    "game_date",
    "player_id",
    "player_name",
    "team",
    "ab",
    "r",
    "h",
    "rbi",
    "bb",
    "hit_by_pitch",
    "home_runs",
    "stolen_bases",
    "batting_opportunity",
    "hit_game",
    "hr_game",
    "rbi_game",
    "run_game",
    "sb_game",
    "walk_game",
    "on_base_game",
]

PARSED_PITCHING_COLUMNS = [
    "season",
    "game_id",
    "game_date",
    "player_id",
    "player_name",
    "team",
    "ip_outs",
    "r_allowed",
    "er_allowed",
    "is_starter",
    "decision",
    "win_game",
    "loss_game",
    "save_game",
    "blown_save",
    "qs_game",
    "scoreless_appearance",
]

SNAPSHOT_COLUMNS = [
    "season",
    "game_id",
    "game_date",
    "player_id",
    "player_name",
    "team",
    "streak_type",
    "streak_label",
    "current_value",
    "ip_outs_accum",
    "run_index",
    "streak_run_id",
]


@dataclass(frozen=True)
class StreakExportResult:
    output_dir: Path
    files: tuple[Path, ...]
    season: int


def export_streak_csvs(
    aggregator: Aggregator,
    output_dir: str | Path,
    season: int,
) -> StreakExportResult:
    """Write streak CSV bundle for one season into *output_dir*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    policies = load_streak_policies()
    labels: dict[str, str] = dict(policies.get("labels") or {})
    tracker = StreakTracker(aggregator)

    written: list[Path] = []

    events_path = out / "streak_milestone_events.csv"
    _write_milestone_events(aggregator, events_path, season, labels)
    written.append(events_path)

    ended_path = out / "ended_streaks.csv"
    _write_milestone_events(
        aggregator,
        ended_path,
        season,
        labels,
        event_type="streak_ended",
    )
    written.append(ended_path)

    state_path = out / "player_streak_state.csv"
    _write_player_streak_state(aggregator, state_path, season, labels)
    written.append(state_path)

    batting_path = out / "parsed_batting_game_logs.csv"
    _write_parsed_batting_logs(aggregator, batting_path, season)
    written.append(batting_path)

    pitching_path = out / "parsed_pitching_game_logs.csv"
    _write_parsed_pitching_logs(aggregator, pitching_path, season)
    written.append(pitching_path)

    _, bat_snapshots, pit_snapshots = tracker.replay_season_with_snapshots(season)

    bat_by_game_path = out / "batting_streaks_by_game.csv"
    _write_csv(bat_by_game_path, SNAPSHOT_COLUMNS, bat_snapshots)
    written.append(bat_by_game_path)

    pit_by_game_path = out / "pitching_streaks_by_game.csv"
    _write_csv(pit_by_game_path, SNAPSHOT_COLUMNS, pit_snapshots)
    written.append(pit_by_game_path)

    return StreakExportResult(output_dir=out, files=tuple(written), season=season)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_milestone_events(
    aggregator: Aggregator,
    path: Path,
    season: int,
    labels: dict[str, str],
    *,
    event_type: str | None = None,
) -> None:
    query = """
        SELECT mr.*,
               COALESCE(p.short_name, p.full_name, '') AS player_name
        FROM milestone_records mr
        LEFT JOIN players p ON p.player_id = mr.player_id
        WHERE mr.scope = 'streak' AND mr.season = ?
    """
    params: list[Any] = [season]
    if event_type:
        query += " AND mr.streak_event_type = ?"
        params.append(event_type)
    query += " ORDER BY mr.achieved_date, mr.game_id, mr.id"

    rows = aggregator.conn.execute(query, params).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        streak_type = str(row["streak_type"] or "")
        output.append(
            {
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team": row["team"] or "",
                "season": row["season"],
                "game_id": row["game_id"],
                "achieved_date": row["achieved_date"] or "",
                "streak_type": streak_type,
                "streak_label": labels.get(streak_type, streak_type),
                "streak_event_type": row["streak_event_type"] or "",
                "milestone_value": row["achieved_value"],
                "milestone_label": row["milestone_label"] or "",
                "streak_run_id": row["streak_run_id"] or "",
                "description": row["description"] or "",
            }
        )
    _write_csv(path, MILESTONE_EVENT_COLUMNS, output)


def _write_player_streak_state(
    aggregator: Aggregator,
    path: Path,
    season: int,
    labels: dict[str, str],
) -> None:
    rows = aggregator.conn.execute(
        """
        SELECT pss.*,
               COALESCE(p.short_name, p.full_name, '') AS player_name
        FROM player_streak_state pss
        LEFT JOIN players p ON p.player_id = pss.player_id
        WHERE pss.season = ?
        ORDER BY pss.player_id, pss.streak_type
        """,
        (season,),
    ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        streak_type = str(row["streak_type"])
        ip_outs = int(row["ip_outs_accum"] or 0)
        current = int(row["current_value"] or 0)
        output.append(
            {
                "season": season,
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "streak_type": streak_type,
                "streak_label": labels.get(streak_type, streak_type),
                "current_value": current,
                "ip_outs_accum": ip_outs,
                "ip_outs_display": outs_to_ip_str(ip_outs),
                "run_index": row["run_index"],
                "last_success_game_id": row["last_success_game_id"] or "",
                "last_success_game_date": row["last_success_game_date"] or "",
                "recorded_milestones": row["recorded_milestones"] or "",
            }
        )
    columns = STATE_COLUMNS + ["ip_outs_display"]
    _write_csv(path, columns, output)


def _write_parsed_batting_logs(
    aggregator: Aggregator, path: Path, season: int
) -> None:
    rows = aggregator.conn.execute(
        """
        SELECT bl.*, COALESCE(p.short_name, p.full_name, '') AS player_name
        FROM batting_logs bl
        LEFT JOIN players p ON p.player_id = bl.player_id
        WHERE bl.season = ?
        ORDER BY bl.date, bl.game_id, bl.id
        """,
        (season,),
    ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        log = batting_log_from_row(dict(row), player_name=str(row["player_name"]))
        output.append(
            {
                "season": log.season,
                "game_id": log.game_id,
                "game_date": log.game_date,
                "player_id": log.player_id,
                "player_name": log.player_name,
                "team": log.team,
                "ab": log.ab,
                "r": log.r,
                "h": log.h,
                "rbi": log.rbi,
                "bb": log.bb,
                "hit_by_pitch": log.hit_by_pitch,
                "home_runs": log.home_runs,
                "stolen_bases": log.stolen_bases,
                "batting_opportunity": int(log.batting_opportunity),
                "hit_game": int(log.hit_game),
                "hr_game": int(log.hr_game_flag),
                "rbi_game": int(log.rbi_game),
                "run_game": int(log.run_game),
                "sb_game": int(log.sb_game_flag),
                "walk_game": int(log.walk_game),
                "on_base_game": int(log.on_base_game),
            }
        )
    _write_csv(path, PARSED_BATTING_COLUMNS, output)


def _write_parsed_pitching_logs(
    aggregator: Aggregator, path: Path, season: int
) -> None:
    rows = aggregator.conn.execute(
        """
        SELECT pl.*,
               COALESCE(pl.is_starter, 0) AS is_starter,
               COALESCE(p.short_name, p.full_name, '') AS player_name
        FROM pitching_logs pl
        LEFT JOIN players p ON p.player_id = pl.player_id
        WHERE pl.season = ?
        ORDER BY pl.date, pl.game_id, pl.id
        """,
        (season,),
    ).fetchall()
    tracker = StreakTracker(aggregator)
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        game_id = int(item["game_id"])
        if not int(item.get("is_starter") or 0):
            item["is_starter"] = tracker._infer_is_starter(
                game_id, str(item["team"]), int(item["id"])
            )
        log = pitching_log_from_row(item, player_name=str(item["player_name"]))
        output.append(
            {
                "season": log.season,
                "game_id": log.game_id,
                "game_date": log.game_date,
                "player_id": log.player_id,
                "player_name": log.player_name,
                "team": log.team,
                "ip_outs": log.ip_outs,
                "r_allowed": log.r_allowed,
                "er_allowed": log.er_allowed,
                "is_starter": int(log.is_starter),
                "decision": log.decision,
                "win_game": int(log.win_game),
                "loss_game": int(log.loss_game),
                "save_game": int(log.save_game),
                "blown_save": int(log.blown_save),
                "qs_game": int(log.qs_game),
                "scoreless_appearance": int(log.scoreless_appearance),
            }
        )
    _write_csv(path, PARSED_PITCHING_COLUMNS, output)
