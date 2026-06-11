"""Milestone achievement prediction (pace-based)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.milestone.checker import (
    CAREER_BATTING_STATS,
    CAREER_PITCHING_STATS,
    SEASON_COUNT_STATS,
    MilestoneChecker,
)
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
    """Estimate season-end milestone attainment based on current pace."""

    def __init__(self, checker: MilestoneChecker, season: int) -> None:
        self.checker = checker
        self.season = season
        self.season_games_total = checker.season_games_total

    def predict_all(self) -> list[MilestonePrediction]:
        predictions: list[MilestonePrediction] = []
        for milestone in self.checker.definitions.all_milestones:
            if milestone.scope != "season":
                continue
            rows = self._rows_for_milestone(milestone)
            for row in rows:
                current = self._current_value(row, milestone)
                if current is None or self.checker._is_achieved(current, milestone):
                    continue
                games = int(row.get("games_played") or row.get("games") or 0)
                projected = self._project_value(current, games)
                remaining = (
                    milestone.threshold - current
                    if milestone.direction == "higher"
                    else current - milestone.threshold
                )
                on_pace = projected is not None and self.checker._is_achieved(
                    projected, milestone
                )
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

    def _rows_for_milestone(self, milestone: MilestoneDefinition) -> list[dict[str, Any]]:
        agg = self.checker.aggregator
        if milestone.category == "batting":
            return agg.get_season_batting_totals(self.season)
        return agg.get_season_pitching_totals(self.season)

    def _current_value(
        self, row: dict[str, Any], milestone: MilestoneDefinition
    ) -> float | None:
        stat = milestone.stat
        if stat in SEASON_COUNT_STATS:
            _, mode, _ = SEASON_COUNT_STATS[stat]
            if mode == "season_hr":
                return float(row.get("hr") or 0)
            if mode == "season_rbi":
                return float(row.get("rbi") or 0)
            if mode == "sum_h":
                return float(row.get("h") or 0)
            if mode == "sum_sb":
                return float(row.get("sb") or 0)
            if mode == "sum_k":
                return float(row.get("k") or 0)
            if mode == "sum_w":
                return float(row.get("w") or 0)
            if mode == "sum_sv":
                return float(row.get("sv") or 0)
        if stat in CAREER_BATTING_STATS:
            return float(row.get(CAREER_BATTING_STATS[stat].replace("career_", ""), 0) or 0)
        if stat in CAREER_PITCHING_STATS:
            key = CAREER_PITCHING_STATS[stat].replace("career_", "")
            return float(row.get(key if key != "wins" else "w", 0) or 0)
        return None

    def _project_value(self, current: float, games: int) -> float | None:
        if games <= 0:
            return None
        pace = current / games
        return pace * self.season_games_total
