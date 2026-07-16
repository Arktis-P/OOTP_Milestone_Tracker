"""Read-only projections for displaying active streaks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.stats.aggregator import Aggregator
from core.streak.policies import format_streak_value, load_streak_policies


@dataclass(frozen=True)
class ActiveStreak:
    season: int
    player_id: int
    player_name: str
    team: str
    streak_type: str
    label: str
    unit: str
    value: int
    display_value: str
    start_date: str
    last_date: str


def _policy_for_type(
    streak_type: str, policies: dict[str, Any]
) -> dict[str, Any]:
    for group in ("batting", "pitching"):
        policy = (policies.get(group) or {}).get(streak_type)
        if isinstance(policy, dict):
            return policy
    return {}


def list_active_streaks(
    aggregator: Aggregator,
    season: int,
    *,
    limit: int = 8,
    policies: dict[str, Any] | None = None,
) -> list[ActiveStreak]:
    """Return active streaks ordered by their most recent successful game.

    Values from different streak types are intentionally not compared.  The
    scoreless-innings state is stored in ``ip_outs_accum`` while counter
    streaks use ``current_value``.
    """
    if limit <= 0:
        return []
    policy_root = policies if policies is not None else load_streak_policies()
    rows = aggregator.conn.execute(
        """
        WITH team_logs AS (
            SELECT player_id, season, team, date, game_id FROM batting_logs
            UNION ALL
            SELECT player_id, season, team, date, game_id FROM pitching_logs
        ),
        latest_teams AS (
            SELECT player_id, season, team
            FROM (
                SELECT player_id, season, team,
                       ROW_NUMBER() OVER (
                           PARTITION BY player_id, season
                           ORDER BY COALESCE(date, '') DESC, game_id DESC
                       ) AS row_num
                FROM team_logs
            )
            WHERE row_num = 1
        )
        SELECT pss.season, pss.player_id, pss.streak_type,
               pss.current_value, pss.ip_outs_accum,
               COALESCE(pss.first_success_game_date, '') AS start_date,
               COALESCE(pss.last_success_game_date, '') AS last_date,
               COALESCE(NULLIF(p.short_name, ''), NULLIF(p.full_name, ''), '')
                   AS player_name,
               COALESCE(NULLIF(lt.team, ''), '') AS team
        FROM player_streak_state pss
        LEFT JOIN players p ON p.player_id = pss.player_id
        LEFT JOIN latest_teams lt
          ON lt.player_id = pss.player_id AND lt.season = pss.season
        WHERE pss.season = ?
        ORDER BY COALESCE(pss.last_success_game_date, '') DESC,
                 COALESCE(pss.last_success_game_id, 0) DESC,
                 player_name COLLATE NOCASE,
                 pss.streak_type
        """,
        (int(season),),
    ).fetchall()

    labels = policy_root.get("labels") or {}
    result: list[ActiveStreak] = []
    for row in rows:
        streak_type = str(row["streak_type"] or "")
        policy = _policy_for_type(streak_type, policy_root)
        current_value = int(row["current_value"] or 0)
        ip_outs_accum = int(row["ip_outs_accum"] or 0)
        if policy:
            is_outs = policy.get("unit") == "outs"
            value = ip_outs_accum if is_outs else current_value
            display_value = format_streak_value(value, policy)
            unit = str(policy.get("display_unit") or ("IP" if is_outs else "games"))
        elif current_value > 0:
            value = current_value
            display_value = str(value)
            unit = "games"
        else:
            value = ip_outs_accum
            display_value = str(value)
            unit = "outs"
        if value <= 0:
            continue
        result.append(
            ActiveStreak(
                season=int(row["season"]),
                player_id=int(row["player_id"]),
                player_name=str(row["player_name"] or "Unknown player"),
                team=str(row["team"] or "Unknown team"),
                streak_type=streak_type,
                label=str(labels.get(streak_type) or streak_type or "Unknown streak"),
                unit=unit,
                value=value,
                display_value=display_value,
                start_date=str(row["start_date"] or ""),
                last_date=str(row["last_date"] or ""),
            )
        )
        if len(result) >= limit:
            break
    return result
