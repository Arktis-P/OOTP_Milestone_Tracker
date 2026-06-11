"""Milestone achievement prediction."""

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

_PITCHING_TOTALS_COL = {
    "career_wins": "w",
    "career_k_pit": "k",
    "career_saves": "sv",
    "career_era": "era",
}

_SEASON_PITCHING_COL = {
    "career_wins": "w",
    "career_k_pit": "k",
    "career_saves": "sv",
}


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


@dataclass
class CareerMilestonePrediction:
    player_id: int
    player_name: str
    milestone: MilestoneDefinition
    current_value: float
    threshold: float
    remaining: float
    progress_pct: float
    season_possible: bool | None
    season_projected_add: float
    season_note: str


class MilestonePredictor:
    """Estimate milestone attainment."""

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

    def predict_career_all(
        self,
        player_ids: list[int] | None = None,
        *,
        achieved_keys: set[tuple[int, str]] | None = None,
        tracked_teams: list[str] | None = None,
    ) -> list[CareerMilestonePrediction]:
        achieved = achieved_keys or set()
        players = self.checker.aggregator.get_tracked_players(tracked_teams)
        if player_ids is not None:
            id_set = set(player_ids)
            players = [player for player in players if player["player_id"] in id_set]
        if not players:
            return []

        agg = self.checker.aggregator
        batting_by_id = {int(row["id"]): row for row in agg.get_career_batting_totals()}
        pitching_by_id = {int(row["id"]): row for row in agg.get_career_pitching_totals()}
        season_batting_by_id = {
            int(row["id"]): row for row in agg.get_season_batting_totals(self.season)
        }
        season_pitching_by_id = {
            int(row["id"]): row for row in agg.get_season_pitching_totals(self.season)
        }

        predictions: list[CareerMilestonePrediction] = []
        for milestone in self.checker.definitions.all_milestones:
            if milestone.scope != "career":
                continue
            for player in players:
                player_id = int(player["player_id"])
                if (player_id, milestone.key) in achieved:
                    continue
                current = self._career_value_from_totals(
                    player_id, milestone, batting_by_id, pitching_by_id
                )
                if current is None:
                    continue
                if self.checker._is_achieved(current, milestone):
                    continue
                remaining = (
                    milestone.threshold - current
                    if milestone.direction == "higher"
                    else current - milestone.threshold
                )
                progress = (
                    (current / milestone.threshold * 100)
                    if milestone.threshold and milestone.direction == "higher"
                    else 0.0
                )
                season_info = self._estimate_this_season_from_totals(
                    player_id,
                    milestone,
                    remaining,
                    season_batting_by_id,
                    season_pitching_by_id,
                )
                predictions.append(
                    CareerMilestonePrediction(
                        player_id=player_id,
                        player_name=str(player.get("full_name") or player.get("short_name")),
                        milestone=milestone,
                        current_value=current,
                        threshold=milestone.threshold,
                        remaining=remaining,
                        progress_pct=round(progress, 1),
                        season_possible=season_info["possible"],
                        season_projected_add=season_info["projected_add"],
                        season_note=season_info["note"],
                    )
                )
        predictions.sort(key=lambda item: item.progress_pct, reverse=True)
        return predictions

    def _career_value_from_totals(
        self,
        player_id: int,
        milestone: MilestoneDefinition,
        batting_by_id: dict[int, dict[str, Any]],
        pitching_by_id: dict[int, dict[str, Any]],
    ) -> float | None:
        stat = milestone.stat
        if stat in CAREER_BATTING_STATS:
            row = batting_by_id.get(player_id)
            if not row:
                return None
            col = CAREER_BATTING_STATS[stat].replace("career_", "")
            return float(row.get(col, 0) or 0)
        if stat in CAREER_PITCHING_STATS:
            row = pitching_by_id.get(player_id)
            if not row:
                return None
            col = _PITCHING_TOTALS_COL.get(stat, stat.replace("career_", ""))
            return float(row.get(col, 0) or 0)
        return None

    def _estimate_this_season_from_totals(
        self,
        player_id: int,
        milestone: MilestoneDefinition,
        remaining: float,
        season_batting_by_id: dict[int, dict[str, Any]],
        season_pitching_by_id: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        stat_key = milestone.stat
        if milestone.category == "batting":
            season_stats = season_batting_by_id.get(player_id)
            col = CAREER_BATTING_STATS.get(stat_key, stat_key).replace("career_", "")
        else:
            season_stats = season_pitching_by_id.get(player_id)
            col = _SEASON_PITCHING_COL.get(stat_key, stat_key)

        if not season_stats:
            return {
                "possible": None,
                "projected_add": 0.0,
                "note": "데이터 없음",
            }

        games_played = int(
            season_stats.get("games_played") or season_stats.get("games") or 0
        )
        current_val = float(season_stats.get(col, 0) or 0)
        if games_played == 0:
            return {
                "possible": False,
                "projected_add": 0.0,
                "note": "데이터 없음",
            }

        per_game = current_val / games_played
        games_remaining = max(self.season_games_total - games_played, 0)
        projected_add = per_game * games_remaining
        possible = projected_add >= remaining
        if possible:
            note = f"가능 (+{projected_add:.0f})"
        else:
            after = max(remaining - projected_add, 0)
            note = f"불가 (+{projected_add:.0f}, 시즌 후 {after:.0f} 남음)"
        return {
            "possible": possible,
            "projected_add": round(projected_add, 1),
            "note": note,
        }

    def _estimate_this_season(
        self, player_id: int, milestone: MilestoneDefinition, remaining: float
    ) -> dict[str, Any]:
        stat_key = milestone.stat
        if milestone.category == "batting":
            season_stats = self.checker.aggregator.get_batting_season(player_id, self.season)
            col = CAREER_BATTING_STATS.get(stat_key, stat_key).replace("career_", "")
        else:
            season_stats = self.checker.aggregator.get_pitching_season(player_id, self.season)
            col = _SEASON_PITCHING_COL.get(stat_key, stat_key)

        if not season_stats:
            return {
                "possible": None,
                "projected_add": 0.0,
                "note": "데이터 없음",
            }

        games_played = int(
            season_stats.get("games_played") or season_stats.get("games") or 0
        )
        current_val = float(season_stats.get(col, 0) or 0)
        if games_played == 0:
            return {
                "possible": False,
                "projected_add": 0.0,
                "note": "데이터 없음",
            }

        per_game = current_val / games_played
        games_remaining = max(self.season_games_total - games_played, 0)
        projected_add = per_game * games_remaining
        possible = projected_add >= remaining
        if possible:
            note = f"가능 (+{projected_add:.0f})"
        else:
            after = max(remaining - projected_add, 0)
            note = f"불가 (+{projected_add:.0f}, 시즌 후 {after:.0f} 남음)"
        return {
            "possible": possible,
            "projected_add": round(projected_add, 1),
            "note": note,
        }

    def _career_value(self, player_id: int, milestone: MilestoneDefinition) -> float | None:
        stat = milestone.stat
        if stat in CAREER_BATTING_STATS:
            key = CAREER_BATTING_STATS[stat]
            return self.checker.aggregator.get_career_batting_stat(player_id, key)
        if stat in CAREER_PITCHING_STATS:
            key = CAREER_PITCHING_STATS[stat]
            return self.checker.aggregator.get_career_pitching_stat(player_id, key)
        return None

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
