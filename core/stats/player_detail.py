"""Read-only player detail summary for the Stats screen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.config import AppSettings
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.implementation import is_award_milestone
from core.milestone.prediction_store import CachedPrediction, PredictionStore
from core.stats.aggregator import Aggregator
from core.streak.policies import format_streak_value, load_streak_policies

EventKind = Literal["milestone", "award", "transfer", "injury", "streak", "other"]


@dataclass(frozen=True)
class PlayerEvent:
    record_id: int
    kind: EventKind
    date: str
    label: str
    description: str
    season: int | None
    game_id: int | None
    grade: str


@dataclass(frozen=True)
class PlayerActiveStreak:
    label: str
    display_value: str
    unit: str
    start_date: str
    last_date: str
    streak_type: str


@dataclass(frozen=True)
class PlayerDetail:
    player_id: int | None
    season: int
    current_team: str
    position: str
    events: list[PlayerEvent]
    active_streaks: list[PlayerActiveStreak]
    next_milestones: list[CachedPrediction]
    status: str


def classify_player_event(
    record: dict[str, Any],
    definition: MilestoneDefinition | None,
) -> EventKind:
    """Classify a player-owned milestone record for compact detail display."""
    key = str(record.get("milestone_key") or "").lower()
    scope = str(record.get("scope") or "").lower()
    streak_event_type = str(record.get("streak_event_type") or "").strip()

    if key.startswith("manual_transfer_"):
        return "transfer"
    if key == "manual_injury" or key.startswith("manual_injury_"):
        return "injury"
    if streak_event_type or scope == "streak" or key.startswith("streak_"):
        return "streak"
    if definition and is_award_milestone(definition):
        return "award"
    if key.startswith(("award_", "title_")) or "_award_" in key or "_title_" in key:
        return "award"
    if scope in {"career", "season", "game", "season_ratio"}:
        return "milestone"
    return "other"


def load_player_detail(
    aggregator: Aggregator,
    milestones: MilestoneDefinitions,
    settings: AppSettings,
    player: dict[str, Any] | None,
    *,
    season: int,
    event_limit: int = 8,
    streak_limit: int = 4,
    next_limit: int = 5,
) -> PlayerDetail:
    if not player:
        return PlayerDetail(
            player_id=None,
            season=season,
            current_team="",
            position="",
            events=[],
            active_streaks=[],
            next_milestones=[],
            status="select_player",
        )

    player_id = int(player["player_id"])
    row = aggregator.conn.execute(
        "SELECT 1 FROM players WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    if row is None:
        return PlayerDetail(
            player_id=player_id,
            season=season,
            current_team="",
            position=str(player.get("primary_position") or ""),
            events=[],
            active_streaks=[],
            next_milestones=[],
            status="missing_player",
        )

    position = str(player.get("primary_position") or "").strip()
    current_team = _latest_team_for_player(aggregator, player_id, season)
    events = _recent_player_events(
        aggregator, milestones, player_id, limit=event_limit
    )
    active_streaks = _active_streaks_for_player(
        aggregator, player_id, season, limit=streak_limit
    )
    next_milestones = PredictionStore(
        aggregator,
        milestones,
        season=season,
        season_games_total=settings.season_games_total,
        tracked_teams=settings.tracked_teams,
        custom_teams=settings.custom_mlb_teams,
    ).list_cached(player_id=player_id)[:next_limit]

    status = ""
    if not events and not active_streaks and not next_milestones:
        status = "empty_detail"

    return PlayerDetail(
        player_id=player_id,
        season=season,
        current_team=current_team,
        position=position,
        events=events,
        active_streaks=active_streaks,
        next_milestones=next_milestones,
        status=status,
    )


def _latest_team_for_player(
    aggregator: Aggregator,
    player_id: int,
    season: int,
) -> str:
    row = aggregator.conn.execute(
        """
        WITH team_rows AS (
            SELECT team, date, game_id, 1 AS source_rank
            FROM batting_logs
            WHERE player_id = ? AND season = ?
            UNION ALL
            SELECT team, date, game_id, 1 AS source_rank
            FROM pitching_logs
            WHERE player_id = ? AND season = ?
            UNION ALL
            SELECT COALESCE(NULLIF(team_abbr, ''), NULLIF(team_name, '')) AS team,
                   printf('%04d-00-00', season) AS date,
                   0 AS game_id,
                   0 AS source_rank
            FROM player_roster
            WHERE player_id = ? AND season = ?
            UNION ALL
            SELECT COALESCE(NULLIF(team_abbr, ''), NULLIF(team_name, '')) AS team,
                   printf('%04d-00-00', season) AS date,
                   0 AS game_id,
                   0 AS source_rank
            FROM player_team_affiliations
            WHERE player_id = ? AND season = ?
        )
        SELECT team
        FROM team_rows
        WHERE COALESCE(team, '') != ''
        ORDER BY source_rank DESC, date DESC, game_id DESC, team
        LIMIT 1
        """,
        (player_id, season, player_id, season, player_id, season, player_id, season),
    ).fetchone()
    if row and row["team"]:
        return str(row["team"])

    row = aggregator.conn.execute(
        """
        WITH team_rows AS (
            SELECT team, date, game_id, 2 AS source_rank
            FROM batting_logs
            WHERE player_id = ?
            UNION ALL
            SELECT team, date, game_id, 2 AS source_rank
            FROM pitching_logs
            WHERE player_id = ?
            UNION ALL
            SELECT COALESCE(NULLIF(team_abbr, ''), NULLIF(team_name, '')) AS team,
                   printf('%04d-00-00', season) AS date,
                   0 AS game_id,
                   1 AS source_rank
            FROM player_roster
            WHERE player_id = ?
            UNION ALL
            SELECT COALESCE(NULLIF(team_abbr, ''), NULLIF(team_name, '')) AS team,
                   printf('%04d-00-00', season) AS date,
                   0 AS game_id,
                   1 AS source_rank
            FROM player_team_affiliations
            WHERE player_id = ?
        )
        SELECT team
        FROM team_rows
        WHERE COALESCE(team, '') != ''
        ORDER BY source_rank DESC, date DESC, game_id DESC, team
        LIMIT 1
        """,
        (player_id, player_id, player_id, player_id),
    ).fetchone()
    return str(row["team"]) if row and row["team"] else ""


def _recent_player_events(
    aggregator: Aggregator,
    milestones: MilestoneDefinitions,
    player_id: int,
    *,
    limit: int,
) -> list[PlayerEvent]:
    if limit <= 0:
        return []
    rows = aggregator.conn.execute(
        """
        SELECT mr.*
        FROM milestone_records mr
        WHERE mr.player_id = ?
          AND mr.player_id > 0
          AND LOWER(COALESCE(mr.scope, '')) NOT LIKE 'team%'
        ORDER BY COALESCE(mr.achieved_date, '') DESC, mr.id DESC
        LIMIT ?
        """,
        (player_id, max(limit * 5, limit)),
    ).fetchall()

    events: list[PlayerEvent] = []
    for row in rows:
        record = dict(row)
        definition = milestones.get_by_key(str(record.get("milestone_key") or ""))
        if definition and definition.category == "team":
            continue
        kind = classify_player_event(record, definition)
        label = (
            str(definition.label)
            if definition
            else str(record.get("milestone_label") or record.get("milestone_key") or "")
        )
        description = str(
            record.get("description") or record.get("notes") or ""
        ).strip()
        game_id = record.get("game_id")
        events.append(
            PlayerEvent(
                record_id=int(record["id"]),
                kind=kind,
                date=str(record.get("achieved_date") or ""),
                label=label,
                description=description,
                season=(
                    int(record["season"])
                    if record.get("season") is not None
                    else None
                ),
                game_id=int(game_id) if game_id is not None else None,
                grade=str((definition.grade if definition else "") or ""),
            )
        )
        if len(events) >= limit:
            break
    return events


def _active_streaks_for_player(
    aggregator: Aggregator,
    player_id: int,
    season: int,
    *,
    limit: int,
) -> list[PlayerActiveStreak]:
    if limit <= 0:
        return []
    try:
        policies = load_streak_policies()
    except (OSError, ValueError):
        policies = {}
    labels = policies.get("labels") or {}
    rows = aggregator.conn.execute(
        """
        SELECT streak_type, current_value, ip_outs_accum,
               COALESCE(first_success_game_date, '') AS start_date,
               COALESCE(last_success_game_date, '') AS last_date
        FROM player_streak_state
        WHERE player_id = ? AND season = ?
        ORDER BY COALESCE(last_success_game_date, '') DESC,
                 COALESCE(last_success_game_id, 0) DESC,
                 streak_type
        """,
        (player_id, season),
    ).fetchall()

    result: list[PlayerActiveStreak] = []
    for row in rows:
        streak_type = str(row["streak_type"] or "")
        policy = _policy_for_type(streak_type, policies)
        current_value = int(row["current_value"] or 0)
        outs = int(row["ip_outs_accum"] or 0)
        if policy:
            is_outs = policy.get("unit") == "outs"
            value = outs if is_outs else current_value
            display_value = format_streak_value(value, policy)
            unit = str(policy.get("display_unit") or ("IP" if is_outs else "games"))
        elif current_value > 0:
            value = current_value
            display_value = str(value)
            unit = "games"
        else:
            value = outs
            display_value = str(value)
            unit = "outs"
        if value <= 0:
            continue
        result.append(
            PlayerActiveStreak(
                label=str(labels.get(streak_type) or streak_type or "Unknown streak"),
                display_value=display_value,
                unit=unit,
                start_date=str(row["start_date"] or ""),
                last_date=str(row["last_date"] or ""),
                streak_type=streak_type,
            )
        )
        if len(result) >= limit:
            break
    return result


def _policy_for_type(streak_type: str, policies: dict[str, Any]) -> dict[str, Any]:
    for group in ("batting", "pitching"):
        policy = (policies.get(group) or {}).get(streak_type)
        if isinstance(policy, dict):
            return policy
    return {}
