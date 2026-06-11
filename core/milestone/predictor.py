"""Milestone achievement prediction (pace-based)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition


@dataclass
class MilestonePrediction:
    player_id: int
    player_name: str
    milestone: MilestoneDefinition
    current_value: float
    projected_value: float | None
    remaining: float
    games_played: int
    on_pace: bool


class MilestonePredictor:
    """Estimate season-end or career milestone attainment based on current pace."""

    def __init__(
        self,
        checker: MilestoneChecker,
        season: int,
        season_games_total: int = 162,
    ) -> None:
        self.checker = checker
        self.season = season
        self.season_games_total = season_games_total

    def predict_all(self) -> list[MilestonePrediction]:
        predictions: list[MilestonePrediction] = []
        for milestone in self.checker.definitions.all_milestones:
            stats = self.checker._stats_for_scope(milestone, self.season)
            for row in stats:
                current = self.checker._resolve_stat_value(row, milestone)
                if current is None:
                    continue
                if current >= milestone.threshold:
                    continue

                games = self._games_played(row, milestone)
                projected = self._project_value(current, games, milestone)
                remaining = milestone.threshold - current
                on_pace = projected is not None and projected >= milestone.threshold

                predictions.append(
                    MilestonePrediction(
                        player_id=int(row["id"]),
                        player_name=str(row["name"]),
                        milestone=milestone,
                        current_value=current,
                        projected_value=projected,
                        remaining=remaining,
                        games_played=games,
                        on_pace=on_pace,
                    )
                )
        return predictions

    def _games_played(self, row: dict[str, Any], milestone: MilestoneDefinition) -> int:
        player_id = int(row["id"])
        conn = self.checker.aggregator.conn
        if milestone.category == "pitching":
            result = conn.execute(
                """
                SELECT COUNT(*) AS games
                FROM pitching_logs
                WHERE player_id = ? AND season = ?
                """,
                (player_id, self.season),
            ).fetchone()
        else:
            result = conn.execute(
                """
                SELECT COUNT(*) AS games
                FROM batting_logs
                WHERE player_id = ? AND season = ?
                """,
                (player_id, self.season),
            ).fetchone()
        return int(result["games"]) if result else 0

    def _project_value(
        self, current: float, games: int, milestone: MilestoneDefinition
    ) -> float | None:
        if milestone.scope == "career":
            return None
        if games <= 0:
            return None
        pace = current / games
        return pace * self.season_games_total
