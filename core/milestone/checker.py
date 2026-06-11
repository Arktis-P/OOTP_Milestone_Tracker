"""Milestone achievement checking."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.stats.aggregator import Aggregator

STAT_RESOLVERS: dict[str, str] = {
    "career_h": "h",
    "career_hr": "hr",
    "career_w": "w",
    "season_h": "h",
    "season_hr": "hr",
    "season_w": "w",
}


@dataclass
class MilestoneAchievement:
    player_id: int
    player_name: str
    milestone: MilestoneDefinition
    current_value: float
    achieved: bool
    achieved_date: str | None = None


class MilestoneChecker:
    """Compare current stats against milestone thresholds."""

    def __init__(self, aggregator: Aggregator, definitions: MilestoneDefinitions) -> None:
        self.aggregator = aggregator
        self.definitions = definitions

    def check_all(self, season: int) -> list[MilestoneAchievement]:
        results: list[MilestoneAchievement] = []
        for milestone in self.definitions.all_milestones:
            stats = self._stats_for_scope(milestone, season)
            for row in stats:
                current = self._resolve_stat_value(row, milestone)
                if current is None:
                    continue
                achieved = current >= milestone.threshold
                results.append(
                    MilestoneAchievement(
                        player_id=int(row["id"]),
                        player_name=str(row["name"]),
                        milestone=milestone,
                        current_value=current,
                        achieved=achieved,
                    )
                )
        return results

    def record_achievements(
        self,
        achievements: list[MilestoneAchievement],
        achieved_date: str,
        season: int,
    ) -> int:
        """Persist newly achieved milestones; skip duplicates."""
        recorded = 0
        conn = self.aggregator.conn
        for item in achievements:
            if not item.achieved:
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO milestone_records
                        (player_id, milestone_key, achieved_date, achieved_value, season)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.player_id,
                        item.milestone.key,
                        achieved_date,
                        item.current_value,
                        season,
                    ),
                )
                conn.commit()
                recorded += 1
            except sqlite3.IntegrityError:
                continue
        return recorded

    def get_recorded_milestones(self) -> list[dict[str, Any]]:
        rows = self.aggregator.conn.execute(
            """
            SELECT mr.id,
                   COALESCE(p.short_name, p.full_name) AS player_name,
                   mr.milestone_key,
                   mr.milestone_label,
                   mr.scope,
                   mr.game_id,
                   mr.achieved_date,
                   mr.achieved_value,
                   mr.season,
                   mr.notes
            FROM milestone_records mr
            JOIN players p ON p.player_id = mr.player_id
            ORDER BY mr.achieved_date DESC, player_name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _stats_for_scope(
        self, milestone: MilestoneDefinition, season: int
    ) -> list[dict[str, Any]]:
        is_pitching = milestone.category == "pitching"
        if milestone.scope == "season":
            if is_pitching:
                return self.aggregator.get_season_pitching_totals(season)
            return self.aggregator.get_season_batting_totals(season)
        if is_pitching:
            return self.aggregator.get_career_pitching_totals()
        return self.aggregator.get_career_batting_totals()

    def _resolve_stat_value(
        self, row: dict[str, Any], milestone: MilestoneDefinition
    ) -> float | None:
        if milestone.stat == "season_avg":
            ab = row.get("ab") or 0
            if ab == 0:
                return None
            return float(row.get("h", 0)) / float(ab)

        column = STAT_RESOLVERS.get(milestone.stat, milestone.stat)
        if column not in row:
            return None
        return float(row[column])
