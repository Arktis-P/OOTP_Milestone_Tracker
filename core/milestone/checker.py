"""Milestone achievement checking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.qualifiers import (
    RatioQualifiers,
    get_batting_qualifier,
    get_pitching_qualifier_outs,
)

Direction = Literal["higher", "lower"]

CAREER_BATTING_STATS = {
    "career_h": "career_h",
    "career_hr": "career_hr",
    "career_rbi": "career_rbi",
    "career_sb": "career_sb",
    "career_bb": "career_bb",
    "career_k_bat": "career_k",
}

CAREER_PITCHING_STATS = {
    "career_wins": "career_wins",
    "career_k_pit": "career_k",
    "career_saves": "career_saves",
    "career_era": "career_era",
}

CAREER_GAME_CONTRIBUTION = {
    "career_h": "h",
    "career_hr": "hr",
    "career_rbi": "rbi",
    "career_sb": "sb",
    "career_bb": "bb",
    "career_k_bat": "k_bat",
    "career_wins": "wins",
    "career_k_pit": "k_pit",
    "career_saves": "saves",
}

SEASON_COUNT_STATS = {
    "season_hr": ("batting", "season_hr", "home_runs"),
    "season_h": ("batting", "sum_h", "h"),
    "season_rbi": ("batting", "season_rbi", "rbi"),
    "season_sb": ("batting", "sum_sb", "sb"),
    "season_k_pit": ("pitching", "sum_k", "k_pit"),
    "season_wins": ("pitching", "sum_w", "season_wins"),
    "season_saves": ("pitching", "sum_sv", "season_saves"),
}

RATIO_BATTING_STATS = {"season_avg", "season_obp", "season_slg", "season_ops"}
RATIO_PITCHING_STATS = {"season_era", "season_whip"}


@dataclass
class MilestoneAchievement:
    player_id: int
    player_name: str
    milestone: MilestoneDefinition
    current_value: float
    achieved: bool
    achieved_date: str | None = None
    game_id: int | None = None
    season: int | None = None


class MilestoneChecker:
    """Compare current stats against milestone thresholds."""

    def __init__(
        self,
        aggregator: Aggregator,
        definitions: MilestoneDefinitions,
        *,
        season_games_total: int = 162,
        ratio_qualifiers: RatioQualifiers | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.definitions = definitions
        self.season_games_total = season_games_total
        self.ratio_qualifiers = ratio_qualifiers or RatioQualifiers()

    def check_new_games(self, game_ids: list[int], season: int) -> list[MilestoneAchievement]:
        achievements: list[MilestoneAchievement] = []
        for game_id in game_ids:
            achievements.extend(self._check_single_game(game_id, season))
        return [item for item in achievements if item.achieved]

    def check_season_ratios(self, season: int) -> list[MilestoneAchievement]:
        achievements: list[MilestoneAchievement] = []
        for milestone in self.definitions.all_milestones:
            if milestone.scope != "season_ratio":
                continue
            if milestone.stat in RATIO_BATTING_STATS:
                rows = self.aggregator.get_season_batting_totals(season)
                min_ab = get_batting_qualifier(self.season_games_total, self.ratio_qualifiers)
                for row in rows:
                    if int(row.get("ab") or 0) < min_ab:
                        continue
                    current = float(row.get(_ratio_column(milestone.stat), 0) or 0)
                    if self._is_achieved(current, milestone):
                        achievements.append(
                            self._build_ratio_achievement(row, milestone, current, season)
                        )
            elif milestone.stat in RATIO_PITCHING_STATS:
                rows = self.aggregator.get_season_pitching_totals(season)
                min_outs = get_pitching_qualifier_outs(
                    self.season_games_total, self.ratio_qualifiers
                )
                for row in rows:
                    if int(row.get("ip_outs") or 0) < min_outs:
                        continue
                    current = float(row.get(_ratio_column(milestone.stat), 0) or 0)
                    if self._is_achieved(current, milestone):
                        achievements.append(
                            self._build_ratio_achievement(row, milestone, current, season)
                        )
        return achievements

    def record_achievements(self, achievements: list[MilestoneAchievement]) -> int:
        recorded = 0
        conn = self.aggregator.conn
        for item in achievements:
            if not item.achieved:
                continue
            if self._achievement_exists(item):
                continue
            conn.execute(
                """
                INSERT INTO milestone_records (
                    player_id, milestone_key, milestone_label, scope,
                    season, game_id, achieved_date, achieved_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.player_id,
                    item.milestone.key,
                    item.milestone.label,
                    item.milestone.scope,
                    item.season,
                    item.game_id,
                    item.achieved_date or "",
                    item.current_value,
                ),
            )
            recorded += 1
        if recorded:
            conn.commit()
        return recorded

    def get_recorded_milestones(
        self,
        *,
        scope: str | None = None,
        season: int | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        query = """
            SELECT mr.id,
                   COALESCE(p.short_name, p.full_name) AS player_name,
                   mr.player_id,
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
            WHERE 1 = 1
        """
        params: list[Any] = []
        if scope:
            query += " AND mr.scope = ?"
            params.append(scope)
        if season is not None:
            query += " AND mr.season = ?"
            params.append(season)
        if search:
            query += " AND (player_name LIKE ? OR mr.milestone_label LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY mr.achieved_date DESC, player_name"
        rows = self.aggregator.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def _check_single_game(self, game_id: int, season: int) -> list[MilestoneAchievement]:
        game = self.aggregator.conn.execute(
            "SELECT date FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        if not game:
            return []
        achieved_date = str(game["date"])
        results: list[MilestoneAchievement] = []

        batting_rows = self.aggregator.conn.execute(
            """
            SELECT bl.*, COALESCE(p.short_name, p.full_name) AS player_name
            FROM batting_logs bl
            JOIN players p ON p.player_id = bl.player_id
            WHERE bl.game_id = ?
            """,
            (game_id,),
        ).fetchall()
        pitching_rows = self.aggregator.conn.execute(
            """
            SELECT pl.*, COALESCE(p.short_name, p.full_name) AS player_name
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            WHERE pl.game_id = ?
            """,
            (game_id,),
        ).fetchall()

        for milestone in self.definitions.all_milestones:
            if milestone.scope == "season_ratio":
                continue
            if milestone.scope == "game":
                if milestone.category == "batting":
                    for row in batting_rows:
                        result = self._check_game_batting_row(
                            dict(row), milestone, game_id, achieved_date, season
                        )
                        if result:
                            results.append(result)
                else:
                    for row in pitching_rows:
                        result = self._check_game_pitching_row(
                            dict(row), milestone, game_id, achieved_date, season
                        )
                        if result:
                            results.append(result)
            elif milestone.scope == "season":
                if milestone.category == "batting":
                    for row in batting_rows:
                        result = self._check_season_batting_row(
                            dict(row), milestone, game_id, achieved_date, season
                        )
                        if result:
                            results.append(result)
                else:
                    for row in pitching_rows:
                        result = self._check_season_pitching_row(
                            dict(row), milestone, game_id, achieved_date, season
                        )
                        if result:
                            results.append(result)
            elif milestone.scope == "career":
                player_ids = {int(row["player_id"]) for row in batting_rows}
                player_ids.update(int(row["player_id"]) for row in pitching_rows)
                names = {
                    int(row["player_id"]): str(row["player_name"])
                    for row in list(batting_rows) + list(pitching_rows)
                }
                for player_id in player_ids:
                    result = self._check_career_player(
                        player_id,
                        names.get(player_id, ""),
                        milestone,
                        game_id,
                        achieved_date,
                        season,
                    )
                    if result:
                        results.append(result)
        return results

    def _check_game_batting_row(
        self,
        row: dict[str, Any],
        milestone: MilestoneDefinition,
        game_id: int,
        achieved_date: str,
        season: int,
    ) -> MilestoneAchievement | None:
        column = _game_batting_column(milestone.stat)
        if not column:
            return None
        current = float(row.get(column, 0) or 0)
        if not self._is_achieved(current, milestone):
            return None
        return MilestoneAchievement(
            player_id=int(row["player_id"]),
            player_name=str(row["player_name"]),
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=achieved_date,
            game_id=game_id,
            season=season,
        )

    def _check_game_pitching_row(
        self,
        row: dict[str, Any],
        milestone: MilestoneDefinition,
        game_id: int,
        achieved_date: str,
        season: int,
    ) -> MilestoneAchievement | None:
        column = _game_pitching_column(milestone.stat)
        if not column:
            return None
        current = float(row.get(column, 0) or 0)
        if not self._is_achieved(current, milestone):
            return None
        return MilestoneAchievement(
            player_id=int(row["player_id"]),
            player_name=str(row["player_name"]),
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=achieved_date,
            game_id=game_id,
            season=season,
        )

    def _check_season_batting_row(
        self,
        row: dict[str, Any],
        milestone: MilestoneDefinition,
        game_id: int,
        achieved_date: str,
        season: int,
    ) -> MilestoneAchievement | None:
        mapping = SEASON_COUNT_STATS.get(milestone.stat)
        if not mapping:
            return None
        _, mode, game_col = mapping
        player_id = int(row["player_id"])
        if mode == "season_hr":
            current = float(row.get("season_hr") or 0)
            prior = self.aggregator.get_max_prior_season_stat(
                player_id, season, game_id, milestone.stat
            ) or 0.0
        elif mode == "season_rbi":
            current = float(row.get("season_rbi") or 0)
            prior = self.aggregator.get_max_prior_season_stat(
                player_id, season, game_id, milestone.stat
            ) or 0.0
        else:
            current = self._season_batting_total(player_id, season, milestone.stat)
            prior = current - float(row.get(game_col, 0) or 0)
        if not self._crossed_threshold(prior, current, milestone):
            return None
        return MilestoneAchievement(
            player_id=player_id,
            player_name=str(row["player_name"]),
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=achieved_date,
            game_id=game_id,
            season=season,
        )

    def _check_season_pitching_row(
        self,
        row: dict[str, Any],
        milestone: MilestoneDefinition,
        game_id: int,
        achieved_date: str,
        season: int,
    ) -> MilestoneAchievement | None:
        mapping = SEASON_COUNT_STATS.get(milestone.stat)
        if not mapping:
            return None
        player_id = int(row["player_id"])
        current = self._season_pitching_total(player_id, season, milestone.stat)
        prior = self.aggregator.get_max_prior_season_pitching_stat(
            player_id, season, game_id, milestone.stat
        )
        if not self._crossed_threshold(prior, current, milestone):
            return None
        return MilestoneAchievement(
            player_id=player_id,
            player_name=str(row["player_name"]),
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=achieved_date,
            game_id=game_id,
            season=season,
        )

    def _check_career_player(
        self,
        player_id: int,
        player_name: str,
        milestone: MilestoneDefinition,
        game_id: int,
        achieved_date: str,
        season: int,
    ) -> MilestoneAchievement | None:
        if milestone.stat in CAREER_BATTING_STATS:
            column = CAREER_BATTING_STATS[milestone.stat]
            current = self.aggregator.get_career_batting_stat(player_id, column)
            game_col = CAREER_GAME_CONTRIBUTION[milestone.stat]
            prior = current - self.aggregator.get_game_contribution_batting(
                player_id, game_id, game_col
            )
        elif milestone.stat in CAREER_PITCHING_STATS:
            column = CAREER_PITCHING_STATS[milestone.stat]
            current = self.aggregator.get_career_pitching_stat(player_id, column)
            if milestone.stat == "career_era":
                return None
            game_col = CAREER_GAME_CONTRIBUTION[milestone.stat]
            prior = current - self.aggregator.get_game_contribution_pitching(
                player_id, game_id, game_col
            )
        else:
            return None

        if not self._crossed_threshold(prior, current, milestone):
            return None
        return MilestoneAchievement(
            player_id=player_id,
            player_name=player_name,
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=achieved_date,
            game_id=game_id,
            season=season,
        )

    def _season_batting_total(self, player_id: int, season: int, stat: str) -> float:
        row = self.aggregator.get_batting_season(player_id, season)
        if not row:
            return 0.0
        if stat == "season_h":
            return float(row.get("h") or 0)
        if stat == "season_sb":
            return float(row.get("sb") or 0)
        return float(row.get(stat.replace("season_", ""), 0) or 0)

    def _season_pitching_total(self, player_id: int, season: int, stat: str) -> float:
        row = self.aggregator.get_pitching_season(player_id, season)
        if not row:
            return 0.0
        if stat == "season_k_pit":
            return float(row.get("k") or 0)
        if stat == "season_wins":
            return float(row.get("wins") or 0)
        if stat == "season_saves":
            return float(row.get("saves") or 0)
        return 0.0

    def _build_ratio_achievement(
        self,
        row: dict[str, Any],
        milestone: MilestoneDefinition,
        current: float,
        season: int,
    ) -> MilestoneAchievement:
        return MilestoneAchievement(
            player_id=int(row["id"]),
            player_name=str(row["name"]),
            milestone=milestone,
            current_value=current,
            achieved=True,
            achieved_date=f"{season}-12-31",
            game_id=None,
            season=season,
        )

    def _achievement_exists(self, item: MilestoneAchievement) -> bool:
        conn = self.aggregator.conn
        scope = item.milestone.scope
        if scope == "career":
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE player_id = ? AND milestone_key = ? AND scope = 'career'
                """,
                (item.player_id, item.milestone.key),
            ).fetchone()
        elif scope in {"season", "season_ratio"}:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE player_id = ? AND milestone_key = ? AND season = ?
                """,
                (item.player_id, item.milestone.key, item.season),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE player_id = ? AND milestone_key = ? AND game_id = ?
                """,
                (item.player_id, item.milestone.key, item.game_id),
            ).fetchone()
        return row is not None

    @staticmethod
    def _is_achieved(current: float, milestone: MilestoneDefinition) -> bool:
        if milestone.direction == "lower":
            return current <= milestone.threshold
        return current >= milestone.threshold

    def _crossed_threshold(
        self, prior: float, current: float, milestone: MilestoneDefinition
    ) -> bool:
        if milestone.direction == "lower":
            return prior > milestone.threshold >= current
        return prior < milestone.threshold <= current


def _game_batting_column(stat: str) -> str | None:
    return {
        "h": "h",
        "hr": "home_runs",
        "rbi": "rbi",
        "bb": "bb",
        "sb": "stolen_bases",
        "doubles": "doubles",
        "k_bat": "k",
    }.get(stat)


def _game_pitching_column(stat: str) -> str | None:
    return {
        "k_pit": "k",
        "ip_outs": "ip_outs",
        "cg": "is_cg",
        "sho": "is_sho",
        "no_hitter": "is_no_hitter",
        "perfect_game": "is_perfect_game",
    }.get(stat)


def _ratio_column(stat: str) -> str:
    return {
        "season_avg": "avg",
        "season_obp": "obp",
        "season_slg": "slg",
        "season_ops": "ops",
        "season_era": "era",
        "season_whip": "whip",
    }.get(stat, stat)
