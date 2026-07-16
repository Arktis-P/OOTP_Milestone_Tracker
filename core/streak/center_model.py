"""Read-only model for the streak center dialog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.stats.aggregator import Aggregator
from core.streak.policies import format_streak_value, load_streak_policies
from core.streak.read_model import ActiveStreak, _policy_for_type, list_active_streaks


@dataclass(frozen=True)
class StreakCenterFilters:
    player: str = ""
    team: str = ""
    streak_type: str = ""
    search: str = ""


@dataclass(frozen=True)
class EndedStreak:
    record_id: int
    season: int
    player_id: int
    player_name: str
    team: str
    streak_type: str
    label: str
    event_type: str
    event_reason: str
    value: int
    display_value: str
    unit: str
    achieved_date: str
    description: str


@dataclass(frozen=True)
class StreakCenterModel:
    active: list[ActiveStreak]
    ended: list[EndedStreak]
    player_options: list[str]
    team_options: list[str]
    type_options: list[tuple[str, str]]
    note: str


def load_streak_center(
    aggregator: Aggregator,
    season: int,
    *,
    filters: StreakCenterFilters | None = None,
    active_limit: int = 100,
    ended_limit: int = 200,
    policies: dict[str, Any] | None = None,
) -> StreakCenterModel:
    """Return active and stored ended streak records for one season.

    This projection intentionally reads only persisted state/events. Ended
    streaks are stored milestone records, not a reconstructed all-time list.
    """
    policy_root = policies if policies is not None else load_streak_policies()
    active = list_active_streaks(
        aggregator,
        season,
        limit=max(0, active_limit),
        policies=policy_root,
    )
    ended = _list_ended_streaks(
        aggregator,
        season,
        limit=max(0, ended_limit),
        policies=policy_root,
    )
    all_rows: list[ActiveStreak | EndedStreak] = [*active, *ended]
    player_options = sorted(
        {row.player_name for row in all_rows if row.player_name},
        key=str.casefold,
    )
    team_options = sorted(
        {row.team for row in all_rows if row.team and row.team != "Unknown team"},
        key=str.casefold,
    )
    type_map = {row.streak_type: row.label for row in all_rows if row.streak_type}
    type_options = sorted(type_map.items(), key=lambda item: item[1].casefold())

    active = _filter_rows(active, filters)
    ended = _filter_rows(ended, filters)
    return StreakCenterModel(
        active=active,
        ended=ended,
        player_options=player_options,
        team_options=team_options,
        type_options=type_options,
        note="Ended and best values shown here are available stored streak records only.",
    )


def _list_ended_streaks(
    aggregator: Aggregator,
    season: int,
    *,
    limit: int,
    policies: dict[str, Any],
) -> list[EndedStreak]:
    if limit <= 0 or not _has_streak_record_columns(aggregator):
        return []
    rows = aggregator.conn.execute(
        """
        SELECT mr.id, mr.season, mr.player_id,
               COALESCE(NULLIF(p.short_name, ''), NULLIF(p.full_name, ''), '')
                   AS player_name,
               COALESCE(NULLIF(mr.team, ''), '') AS team,
               COALESCE(NULLIF(mr.streak_type, ''), '') AS streak_type,
               COALESCE(NULLIF(mr.milestone_label, ''), '') AS milestone_label,
               COALESCE(NULLIF(mr.streak_event_type, ''), '') AS streak_event_type,
               COALESCE(mr.achieved_value, 0) AS achieved_value,
               COALESCE(NULLIF(mr.achieved_date, ''), '') AS achieved_date,
               COALESCE(NULLIF(mr.description, ''), '') AS description
        FROM milestone_records mr
        LEFT JOIN players p ON p.player_id = mr.player_id
        WHERE mr.scope = 'streak'
          AND mr.season = ?
          AND mr.player_id != 0
          AND COALESCE(mr.streak_event_type, '') != ''
        ORDER BY COALESCE(mr.achieved_date, '') DESC, mr.id DESC
        LIMIT ?
        """,
        (int(season), int(limit)),
    ).fetchall()

    labels = policies.get("labels") or {}
    result: list[EndedStreak] = []
    for row in rows:
        streak_type = str(row["streak_type"] or "")
        label = str(row["milestone_label"] or labels.get(streak_type) or streak_type)
        value = int(float(row["achieved_value"] or 0))
        policy = _policy_for_type(streak_type, policies)
        if policy:
            display_value = format_streak_value(value, policy)
            unit = str(
                policy.get("display_unit")
                or ("IP" if policy.get("unit") == "outs" else "games")
            )
        else:
            display_value = str(value)
            unit = ""
        event_type = str(row["streak_event_type"] or "")
        result.append(
            EndedStreak(
                record_id=int(row["id"]),
                season=int(row["season"]),
                player_id=int(row["player_id"]),
                player_name=str(row["player_name"] or "Unknown player"),
                team=str(row["team"] or "Unknown team"),
                streak_type=streak_type,
                label=label or "Unknown streak",
                event_type=event_type,
                event_reason=_event_reason(event_type),
                value=value,
                display_value=display_value,
                unit=unit,
                achieved_date=str(row["achieved_date"] or ""),
                description=str(row["description"] or ""),
            )
        )
    return result


def _has_streak_record_columns(aggregator: Aggregator) -> bool:
    rows = aggregator.conn.execute("PRAGMA table_info(milestone_records)").fetchall()
    columns = {str(row["name"]) for row in rows}
    return {"streak_event_type", "streak_type", "description"}.issubset(columns)


def _event_reason(event_type: str) -> str:
    if event_type == "streak_ended":
        return "Ended"
    if event_type == "streak_milestone":
        return "Milestone"
    return event_type.replace("_", " ").strip().title() or "Stored record"


def _filter_rows(
    rows: list[ActiveStreak] | list[EndedStreak],
    filters: StreakCenterFilters | None,
) -> Any:
    if filters is None:
        return rows
    player = filters.player.casefold().strip()
    team = filters.team.casefold().strip()
    streak_type = filters.streak_type.strip()
    search = filters.search.casefold().strip()
    if not any((player, team, streak_type, search)):
        return rows
    result = []
    for row in rows:
        if player and row.player_name.casefold() != player:
            continue
        if team and row.team.casefold() != team:
            continue
        if streak_type and row.streak_type != streak_type:
            continue
        if search:
            haystack = " ".join(
                str(part)
                for part in (
                    row.player_name,
                    row.team,
                    row.label,
                    row.streak_type,
                    getattr(row, "description", ""),
                    getattr(row, "achieved_date", ""),
                    getattr(row, "start_date", ""),
                    getattr(row, "last_date", ""),
                )
            ).casefold()
            if search not in haystack:
                continue
        result.append(row)
    return result
