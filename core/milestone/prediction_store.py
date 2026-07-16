"""Cached career milestone predictions (watch list + incremental updates)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.i18n import tr
from core.milestone import estimate as pace_estimate
from core.milestone.checker import CAREER_BATTING_STATS, CAREER_PITCHING_STATS, MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.predictor import is_near, qualifies_for_watch
from core.stats.aggregator import Aggregator

_PITCHING_TOTALS_COL = {
    "career_wins": "w",
    "career_gs": "gs",
    "career_k_pit": "k",
    "career_saves": "sv",
    "career_holds": "holds",
    "career_era": "era",
}

_PITCHING_PLAYER_CAREER_STATS = {"career_gs", "career_holds"}
_LogCache = dict[tuple[str, int], list[dict[str, Any]]]


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
    is_near: bool = False
    milestone: MilestoneDefinition | None = None
    pace: pace_estimate.PaceEstimate | None = None


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
        from core.milestone.definitions import PREDICTABLE_SCOPES

        self._career_milestones = [
            milestone
            for milestone in milestones.active_milestones
            if milestone.scope in PREDICTABLE_SCOPES
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
        log_cache: _LogCache = {}

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
                    season_batting,
                    season_pitching,
                    log_cache,
                )
                upserts.append(row)

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
            remaining = float(row["remaining"])
            near = bool(milestone and is_near(remaining, milestone))
            raw_note = str(row["season_note"])
            pace = pace_estimate.decode_pace_estimate(raw_note)
            results.append(
                CachedPrediction(
                    player_id=int(row["player_id"]),
                    player_name=str(row["player_name"]),
                    milestone_key=str(row["milestone_key"]),
                    milestone_label=str(row["milestone_label"]),
                    grade=str(row["grade"]),
                    current_value=float(row["current_value"]),
                    threshold=float(row["threshold"]),
                    remaining=remaining,
                    progress_pct=float(row["progress_pct"]),
                    season_note=raw_note,
                    is_near=near,
                    milestone=milestone,
                    pace=pace,
                )
            )
        results.sort(key=lambda item: (not item.is_near, -item.progress_pct))
        return results

    def list_near_cached(self, *, limit: int = 10) -> list[CachedPrediction]:
        near = [item for item in self.list_cached() if item.is_near]
        return near[:limit]

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
        log_cache: _LogCache = {}
        pitching_career_by_id = (
            {
                player_id: self.aggregator.get_pitching_career(player_id)
                for player_id in player_ids
            }
            if any(
                milestone.stat in _PITCHING_PLAYER_CAREER_STATS
                for milestone in self._career_milestones
            )
            else {}
        )
        for player in players:
            player_id = int(player["player_id"])
            player_name = str(player.get("full_name") or player.get("short_name"))
            for milestone in self._career_milestones:
                if (player_id, milestone.key) in achieved:
                    continue
                if milestone.stat in _PITCHING_PLAYER_CAREER_STATS:
                    current = self._career_value_from_player(
                        milestone, None, pitching_career_by_id.get(player_id)
                    )
                else:
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
                        season_batting_by_id,
                        season_pitching_by_id,
                        log_cache,
                    )
                )
        return rows

    def _make_row(
        self,
        player_id: int,
        player_name: str,
        milestone: MilestoneDefinition,
        current: float,
        season_batting: dict[int, dict[str, Any]],
        season_pitching: dict[int, dict[str, Any]],
        log_cache: _LogCache | None = None,
    ) -> dict[str, Any]:
        remaining = milestone.threshold - current
        progress = (
            (current / milestone.threshold * 100) if milestone.threshold else 0.0
        )
        estimate = self._pace_estimate(
            player_id,
            milestone,
            remaining,
            season_batting,
            season_pitching,
            log_cache,
        )
        season_note = pace_estimate.encode_pace_estimate(estimate)
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
        remaining = (
            milestone.threshold - current
            if milestone.direction == "higher"
            else current - milestone.threshold
        )
        return qualifies_for_watch(remaining, milestone)

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

    def _pace_estimate(
        self,
        player_id: int,
        milestone: MilestoneDefinition,
        remaining: float,
        season_batting: dict[int, dict[str, Any]],
        season_pitching: dict[int, dict[str, Any]],
        log_cache: _LogCache | None = None,
    ) -> pace_estimate.PaceEstimate:
        stat_key = milestone.stat
        if not pace_estimate.is_stat_supported(stat_key, milestone.direction, milestone.category):
            return pace_estimate.PaceEstimate(
                available=False, reason=pace_estimate.REASON_UNSUPPORTED, remaining=remaining
            )

        if milestone.category == "batting":
            season_stats = season_batting.get(player_id)
            col = pace_estimate.batting_season_column(stat_key)
        else:
            season_stats = season_pitching.get(player_id)
            col = pace_estimate.pitching_season_column(stat_key)

        if not season_stats:
            return pace_estimate.PaceEstimate(
                available=False, reason=pace_estimate.REASON_NO_DATA, remaining=remaining
            )

        if milestone.category == "pitching":
            games_played = int(season_stats.get("team_games_elapsed") or 0)
        else:
            games_played = int(
                season_stats.get("games_played") or season_stats.get("games") or 0
            )
        if games_played <= 0:
            return pace_estimate.PaceEstimate(
                available=False, reason=pace_estimate.REASON_NO_DATA, remaining=remaining
            )
        logs: list[dict[str, Any]] | None = None
        recent_values: list[float] = []
        if milestone.category == "pitching" and col not in season_stats:
            logs = self._cached_game_logs(log_cache, "pitching", player_id)
            recent_values = pace_estimate.pitching_recent_values(stat_key, logs) or []
            current_val = float(sum(recent_values))
        else:
            current_val = float(season_stats.get(col, 0) or 0)

        if milestone.category == "batting":
            logs = self._cached_game_logs(log_cache, "batting", player_id)
            recent_values = pace_estimate.batting_recent_values(stat_key, logs) or []
        else:
            if logs is None:
                logs = self._cached_game_logs(log_cache, "pitching", player_id)
            # Pitcher appearances are not a defensible proxy for team games
            # elapsed, so keep the secondary recent basis unavailable unless
            # a future data source can provide zero-filled team-game values.
            recent_values = []

        return pace_estimate.estimate_pace(
            current_value=current_val,
            games_played_season=games_played,
            season_games_total=self.season_games_total,
            remaining=remaining,
            recent_game_values=recent_values,
            direction=milestone.direction,
        )

    def _cached_game_logs(
        self,
        log_cache: _LogCache | None,
        category: str,
        player_id: int,
    ) -> list[dict[str, Any]]:
        if log_cache is None:
            log_cache = {}
        key = (category, player_id)
        if key not in log_cache:
            if category == "batting":
                logs = self.aggregator.get_player_batting_game_logs(
                    player_id, self.season
                )
            else:
                logs = self.aggregator.get_player_pitching_game_logs(
                    player_id, self.season
                )
            log_cache[key] = list(logs)
        return log_cache[key]


def render_season_note(note: str) -> str:
    """Translate a stored season_note (pace-estimate encoding) for display."""
    estimate = pace_estimate.decode_pace_estimate(note)
    if estimate is not None:
        return pace_estimate.render_pace_summary(estimate)
    # Legacy encodings from before the pace-estimate module existed.
    if note == "pre_season":
        return tr("No games yet")
    if note.startswith("achievable|"):
        amount = note[len("achievable|"):]
        return tr("Achievable (+{amount})").format(amount=amount)
    if note.startswith("not_achievable|"):
        parts = note.split("|")
        if len(parts) == 3:
            return tr("Not achievable (+{amount}, {after} remaining after season)").format(
                amount=parts[1], after=parts[2]
            )
    return tr(note) if note else ""


def render_season_basis(note: str) -> str:
    """Full tooltip-style explanation of the basis behind ``note``."""
    estimate = pace_estimate.decode_pace_estimate(note)
    return pace_estimate.render_pace_basis(estimate)
