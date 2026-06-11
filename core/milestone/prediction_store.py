"""Cached career milestone predictions (watch list + incremental updates)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.milestone.checker import CAREER_BATTING_STATS, CAREER_PITCHING_STATS, MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.stats.aggregator import Aggregator

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
class CachedPrediction:
    player_id: int
    player_name: str
    milestone_key: str
    milestone_label: str
    grade: str
    current_value: float
    threshold: float
    remaining: float
    progress_pct: float
    season_note: str
    milestone: MilestoneDefinition | None = None


class PredictionStore:
    """Manage persisted career milestone watch list and incremental updates."""

    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        *,
        season: int,
        season_games_total: int,
        tracked_teams: list[str] | None = None,
        custom_teams: dict[str, str] | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.milestones = milestones
        self.season = season
        self.season_games_total = season_games_total
        self.tracked_teams = tracked_teams or []
        self.custom_teams = custom_teams or {}
        self._career_milestones = [
            milestone
            for milestone in milestones.all_milestones
            if milestone.scope == "career"
        ]

    def is_seeded(self) -> bool:
        return self.aggregator.count_milestone_predictions(self.season) > 0

    def ensure_seeded(self) -> int:
        if self.is_seeded():
            return self.aggregator.count_milestone_predictions(self.season)
        return self.reseed()

    def reseed(self) -> int:
        self.aggregator.clear_milestone_predictions(self.season)
        rows = self._build_watch_rows()
        self.aggregator.upsert_milestone_predictions(rows)
        return len(rows)

    def update_after_import(self, game_ids: list[int]) -> int:
        if not game_ids:
            return 0
        player_ids = self.aggregator.get_player_ids_for_games(game_ids)
        if not player_ids:
            return 0

        achieved = self._achieved_career_keys()
        tracked_ids = self._tracked_player_ids()
        player_ids = {pid for pid in player_ids if pid in tracked_ids}
        if not player_ids:
            return 0

        if not self.is_seeded():
            return self.reseed()

        existing = {
            (row["player_id"], row["milestone_key"]): row
            for row in self.aggregator.get_milestone_predictions(self.season)
            if row["player_id"] in player_ids
        }
        players_by_id = {
            int(player["player_id"]): player
            for player in self.aggregator.get_tracked_players(
                self.tracked_teams, custom_teams=self.custom_teams
            )
            if int(player["player_id"]) in player_ids
        }

        season_batting = {
            int(row["id"]): row
            for row in self.aggregator.get_season_batting_totals(self.season)
            if int(row["id"]) in player_ids
        }
        season_pitching = {
            int(row["id"]): row
            for row in self.aggregator.get_season_pitching_totals(self.season)
            if int(row["id"]) in player_ids
        }

        upserts: list[dict[str, Any]] = []
        deletes: list[tuple[int, str]] = []

        for player_id in player_ids:
            player = players_by_id.get(player_id)
            if not player:
                continue
            player_name = str(player.get("full_name") or player.get("short_name"))
            batting = self.aggregator.get_batting_career(player_id)
            pitching = self.aggregator.get_pitching_career(player_id)

            for milestone in self._career_milestones:
                if (player_id, milestone.key) in achieved:
                    if (player_id, milestone.key) in existing:
                        deletes.append((player_id, milestone.key))
                    continue

                current = self._career_value_from_player(
                    milestone, batting, pitching
                )
                if current is None:
                    continue

                qualifies = self._qualifies_for_watch(milestone, current)
                if not qualifies:
                    if (player_id, milestone.key) in existing:
                        deletes.append((player_id, milestone.key))
                    continue

                row = self._make_row(
                    player_id,
                    player_name,
                    milestone,
                    current,
                    season_batting.get(player_id),
                    season_pitching.get(player_id),
                )
                upserts.append(row)
                watched_keys.discard(milestone.key)

        if deletes:
            self.aggregator.delete_milestone_predictions(self.season, deletes)
        if upserts:
            self.aggregator.upsert_milestone_predictions(upserts)
        return len(upserts)

    def list_cached(
        self,
        *,
        player_id: int | None = None,
        grade: str = "",
    ) -> list[CachedPrediction]:
        rows = self.aggregator.get_milestone_predictions(
            self.season,
            player_id=player_id,
            tracked_teams=self.tracked_teams or None,
            custom_teams=self.custom_teams or None,
        )
        results: list[CachedPrediction] = []
        for row in rows:
            if grade and row["grade"] != grade:
                continue
            milestone = self.milestones.get_by_key(row["milestone_key"])
            results.append(
                CachedPrediction(
                    player_id=int(row["player_id"]),
                    player_name=str(row["player_name"]),
                    milestone_key=str(row["milestone_key"]),
                    milestone_label=str(row["milestone_label"]),
                    grade=str(row["grade"]),
                    current_value=float(row["current_value"]),
                    threshold=float(row["threshold"]),
                    remaining=float(row["remaining"]),
                    progress_pct=float(row["progress_pct"]),
                    season_note=str(row["season_note"]),
                    milestone=milestone,
                )
            )
        results.sort(key=lambda item: item.progress_pct, reverse=True)
        return results

    def _build_watch_rows(self) -> list[dict[str, Any]]:
        achieved = self._achieved_career_keys()
        players = self.aggregator.get_tracked_players(
            self.tracked_teams, custom_teams=self.custom_teams
        )
        if not players:
            return []

        player_ids = {int(player["player_id"]) for player in players}
        batting_by_id = {
            int(row["id"]): row
            for row in self.aggregator.get_career_batting_totals()
            if int(row["id"]) in player_ids
        }
        pitching_by_id = {
            int(row["id"]): row
            for row in self.aggregator.get_career_pitching_totals()
            if int(row["id"]) in player_ids
        }
        season_batting_by_id = {
            int(row["id"]): row
            for row in self.aggregator.get_season_batting_totals(self.season)
            if int(row["id"]) in player_ids
        }
        season_pitching_by_id = {
            int(row["id"]): row
            for row in self.aggregator.get_season_pitching_totals(self.season)
            if int(row["id"]) in player_ids
        }

        rows: list[dict[str, Any]] = []
        for player in players:
            player_id = int(player["player_id"])
            player_name = str(player.get("full_name") or player.get("short_name"))
            for milestone in self._career_milestones:
                if (player_id, milestone.key) in achieved:
                    continue
                current = self._career_value_from_totals(
                    player_id,
                    milestone,
                    batting_by_id,
                    pitching_by_id,
                )
                if current is None or not self._qualifies_for_watch(milestone, current):
                    continue
                rows.append(
                    self._make_row(
                        player_id,
                        player_name,
                        milestone,
                        current,
                        season_batting_by_id.get(player_id),
                        season_pitching_by_id.get(player_id),
                    )
                )
        return rows

    def _make_row(
        self,
        player_id: int,
        player_name: str,
        milestone: MilestoneDefinition,
        current: float,
        season_batting: dict[str, Any] | None,
        season_pitching: dict[str, Any] | None,
    ) -> dict[str, Any]:
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
        season_note = self._season_note(
            milestone, remaining, season_batting, season_pitching
        )
        return {
            "player_id": player_id,
            "milestone_key": milestone.key,
            "season": self.season,
            "player_name": player_name,
            "milestone_label": milestone.label,
            "grade": milestone.grade,
            "current_value": current,
            "threshold": milestone.threshold,
            "remaining": remaining,
            "progress_pct": round(progress, 1),
            "season_note": season_note,
        }

    def _achieved_career_keys(self) -> set[tuple[int, str]]:
        checker = MilestoneChecker(self.aggregator, self.milestones)
        return {
            (int(row["player_id"]), str(row["milestone_key"]))
            for row in checker.get_recorded_milestones(scope="career")
        }

    def _tracked_player_ids(self) -> set[int]:
        return {
            int(player["player_id"])
            for player in self.aggregator.get_tracked_players(
                self.tracked_teams, custom_teams=self.custom_teams
            )
        }

    @staticmethod
    def _qualifies_for_watch(milestone: MilestoneDefinition, current: float) -> bool:
        if MilestoneChecker._is_achieved(current, milestone):
            return False
        if milestone.direction == "higher":
            return current >= milestone.effective_track_from()
        return current <= milestone.effective_track_from()

    @staticmethod
    def _career_value_from_totals(
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

    @staticmethod
    def _career_value_from_player(
        milestone: MilestoneDefinition,
        batting: dict[str, Any] | None,
        pitching: dict[str, Any] | None,
    ) -> float | None:
        stat = milestone.stat
        if stat in CAREER_BATTING_STATS:
            if not batting:
                return None
            key = CAREER_BATTING_STATS[stat]
            return float(batting.get(key, 0) or 0)
        if stat in CAREER_PITCHING_STATS:
            if not pitching:
                return None
            key = CAREER_PITCHING_STATS[stat]
            return float(pitching.get(key, 0) or 0)
        return None

    def _season_note(
        self,
        milestone: MilestoneDefinition,
        remaining: float,
        season_batting: dict[str, Any] | None,
        season_pitching: dict[str, Any] | None,
    ) -> str:
        stat_key = milestone.stat
        if milestone.category == "batting":
            season_stats = season_batting
            col = CAREER_BATTING_STATS.get(stat_key, stat_key).replace("career_", "")
        else:
            season_stats = season_pitching
            col = _SEASON_PITCHING_COL.get(stat_key, stat_key)

        if not season_stats:
            return "시즌 전 — 달성 가능성 미정"

        games_played = int(
            season_stats.get("games_played") or season_stats.get("games") or 0
        )
        if games_played == 0:
            return "시즌 전 — 달성 가능성 미정"

        current_val = float(season_stats.get(col, 0) or 0)
        per_game = current_val / games_played
        games_remaining = max(self.season_games_total - games_played, 0)
        projected_add = per_game * games_remaining
        if projected_add >= remaining:
            return f"가능 (+{projected_add:.0f})"
        after = max(remaining - projected_add, 0)
        return f"불가 (+{projected_add:.0f}, 시즌 후 {after:.0f} 남음)"
