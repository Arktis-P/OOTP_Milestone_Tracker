"""Milestone achievement checking."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from core.milestone.definitions import (
    ACTIVE_SCOPES,
    MilestoneDefinition,
    MilestoneDefinitions,
)
from core.milestone.team_milestone import get_team_wins, team_stat_value
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
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
    team: str | None = None
    notes: str | None = None


class MilestoneChecker:
    """Compare current stats against milestone thresholds."""

    def __init__(
        self,
        aggregator: Aggregator,
        definitions: MilestoneDefinitions,
        *,
        season_games_total: int = 162,
        ratio_qualifiers: RatioQualifiers | None = None,
        tracked_teams: list[str] | None = None,
        custom_teams: dict[str, str] | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.definitions = definitions
        self.season_games_total = season_games_total
        self.ratio_qualifiers = ratio_qualifiers or RatioQualifiers()
        self.tracked_teams = tracked_teams or []
        self.custom_teams = custom_teams or {}
        self._batting_season_cache: dict[tuple[int, int], dict[str, Any] | None] = {}
        self._pitching_season_cache: dict[tuple[int, int], dict[str, Any] | None] = {}
        self._career_batting_cache: dict[int, dict[str, Any] | None] = {}
        self._career_pitching_cache: dict[int, dict[str, Any] | None] = {}

    def check_new_games(
        self,
        game_ids: list[int],
        season: int,
        *,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[MilestoneAchievement]:
        self._clear_stat_caches()
        achievements: list[MilestoneAchievement] = []
        total = len(game_ids)
        for index, game_id in enumerate(game_ids, start=1):
            if progress_callback:
                progress_callback(index, total, f"game {game_id}")
            achievements.extend(self._check_single_game(game_id, season))
        return [item for item in achievements if item.achieved]

    def check_team_season_for_teams(
        self, teams: list[str], season: int
    ) -> list[MilestoneAchievement]:
        """Check team_season milestones (e.g. win totals) for given teams."""
        results: list[MilestoneAchievement] = []
        for team in teams:
            results.extend(self._check_team_season(team, season))
        return [item for item in results if item.achieved]

    def _clear_stat_caches(self) -> None:
        self._batting_season_cache.clear()
        self._pitching_season_cache.clear()
        self._career_batting_cache.clear()
        self._career_pitching_cache.clear()

    def _batting_season_cached(self, player_id: int, season: int) -> dict[str, Any] | None:
        key = (player_id, season)
        if key not in self._batting_season_cache:
            self._batting_season_cache[key] = self.aggregator.get_batting_season(
                player_id, season
            )
        return self._batting_season_cache[key]

    def _pitching_season_cached(self, player_id: int, season: int) -> dict[str, Any] | None:
        key = (player_id, season)
        if key not in self._pitching_season_cache:
            self._pitching_season_cache[key] = self.aggregator.get_pitching_season(
                player_id, season
            )
        return self._pitching_season_cache[key]

    def _career_batting_cached(self, player_id: int) -> dict[str, Any] | None:
        if player_id not in self._career_batting_cache:
            self._career_batting_cache[player_id] = self.aggregator.get_batting_career(
                player_id
            )
        return self._career_batting_cache[player_id]

    def _career_pitching_cached(self, player_id: int) -> dict[str, Any] | None:
        if player_id not in self._career_pitching_cache:
            self._career_pitching_cache[player_id] = self.aggregator.get_pitching_career(
                player_id
            )
        return self._career_pitching_cache[player_id]

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
                    season, game_id, achieved_date, achieved_value, team, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    item.team,
                    item.notes,
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
        subject: str = "all",
        team: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT mr.id,
                   CASE
                       WHEN mr.team IS NOT NULL AND mr.team != '' THEN mr.team
                       ELSE COALESCE(p.short_name, p.full_name, '')
                   END AS player_name,
                   mr.player_id,
                   mr.milestone_key,
                   mr.milestone_label,
                   mr.scope,
                   mr.game_id,
                   mr.achieved_date,
                   mr.achieved_value,
                   mr.season,
                   mr.notes,
                   mr.team,
                   mr.opponent_team,
                   mr.opponent_player,
                   mr.description,
                   mr.games_at_achievement,
                   mr.is_manual
            FROM milestone_records mr
            LEFT JOIN players p ON p.player_id = mr.player_id
            WHERE 1 = 1
        """
        params: list[Any] = []
        if scope:
            query += " AND mr.scope = ?"
            params.append(scope)
        if season is not None:
            query += " AND mr.season = ?"
            params.append(season)
        if subject == "personal":
            query += " AND (mr.team IS NULL OR mr.team = '')"
        elif subject == "team":
            query += " AND mr.team IS NOT NULL AND mr.team != ''"
        if team:
            query += " AND mr.team = ?"
            params.append(team)
        if search:
            query += """
                AND (
                    player_name LIKE ? OR mr.milestone_label LIKE ?
                    OR mr.team LIKE ?
                )
            """
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY mr.achieved_date DESC, player_name"
        rows = self.aggregator.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def record_manual_milestone(self, form) -> int:
        from core.milestone.manual_entry import ManualMilestoneFormData

        if not isinstance(form, ManualMilestoneFormData):
            raise TypeError("expected ManualMilestoneFormData")

        milestone = self.definitions.get_by_key(form.milestone_key)
        if milestone is None:
            raise ValueError(f"Unknown milestone: {form.milestone_key}")

        player_id = int(form.player_id or 0)
        team = (form.team or "").strip() or None
        if form.target == "team":
            player_id = 0
        else:
            team = None

        conn = self.aggregator.conn
        conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope,
                season, game_id, achieved_date, achieved_value,
                team, notes, opponent_team, opponent_player,
                description, games_at_achievement, is_manual
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                player_id,
                milestone.key,
                milestone.label,
                milestone.scope,
                form.season,
                None,
                form.achieved_date.isoformat(),
                float(form.achieved_value),
                team,
                form.notes or None,
                form.opponent_team or None,
                form.opponent_player or None,
                form.description or None,
                form.games_at_achievement,
            ),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def record_manual_team_milestone(
        self,
        *,
        team: str,
        milestone_key: str,
        season: int,
        achieved_date: str,
        notes: str = "",
    ) -> bool:
        milestone = self.definitions.get_by_key(milestone_key)
        if not milestone or milestone.scope != "team_manual":
            raise ValueError(f"Unknown team_manual milestone: {milestone_key}")
        item = MilestoneAchievement(
            player_id=0,
            player_name=team,
            milestone=milestone,
            current_value=1.0,
            achieved=True,
            achieved_date=achieved_date,
            season=season,
            team=team,
            notes=notes or None,
        )
        if self._achievement_exists(item):
            return False
        return self.record_achievements([item]) == 1

    def _check_single_game(self, game_id: int, season: int) -> list[MilestoneAchievement]:
        game = self.aggregator.conn.execute(
            "SELECT date, is_mlb FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        if not game or not int(game["is_mlb"]):
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

        for milestone in self.definitions.active_milestones:
            if milestone.scope not in ACTIVE_SCOPES:
                continue
            if milestone.scope.startswith("team_"):
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

        for team in self._tracked_teams_in_game(game_id):
            results.extend(self._check_team_game(game_id, team, season, achieved_date))
            results.extend(
                self._check_team_season(team, season, achieved_date, game_id=game_id)
            )
        return results

    def _tracked_teams_in_game(self, game_id: int) -> list[str]:
        if not self.tracked_teams:
            return []
        row = self.aggregator.conn.execute(
            "SELECT away_team, home_team FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if not row:
            return []
        names = set(
            expand_tracked_teams(self.tracked_teams, self.custom_teams)
        )
        tokens = {token.strip().upper() for token in self.tracked_teams if token.strip()}
        matched: list[str] = []
        for team_name in (str(row["away_team"]), str(row["home_team"])):
            if team_name in names or team_name.upper() in tokens:
                matched.append(team_name)
        return matched

    def _check_team_game(
        self, game_id: int, team: str, season: int, achieved_date: str
    ) -> list[MilestoneAchievement]:
        conn = self.aggregator.conn
        results: list[MilestoneAchievement] = []
        for milestone in self.definitions.active_milestones:
            if milestone.scope != "team_game":
                continue
            current = team_stat_value(
                conn,
                scope=milestone.scope,
                stat=milestone.stat,
                team=team,
                game_id=game_id,
                season=season,
            )
            if current is None or not self._is_achieved(current, milestone):
                continue
            results.append(
                MilestoneAchievement(
                    player_id=0,
                    player_name=team,
                    milestone=milestone,
                    current_value=current,
                    achieved=True,
                    achieved_date=achieved_date,
                    game_id=game_id,
                    season=season,
                    team=team,
                )
            )
        return results

    def _check_team_season(
        self,
        team: str,
        season: int,
        achieved_date: str | None = None,
        *,
        game_id: int | None = None,
    ) -> list[MilestoneAchievement]:
        conn = self.aggregator.conn
        wins = get_team_wins(conn, team, season)
        prior_wins = wins
        if game_id is not None:
            game = conn.execute(
                """
                SELECT home_team, away_team, home_score, away_score
                FROM games WHERE game_id = ?
                """,
                (game_id,),
            ).fetchone()
            if game and self._team_won_game(team, dict(game)):
                prior_wins = max(0, wins - 1)
        date = achieved_date or f"{season}-12-31"
        results: list[MilestoneAchievement] = []
        for milestone in self.definitions.active_milestones:
            if milestone.scope != "team_season":
                continue
            prior = float(prior_wins)
            current = float(wins)
            if not self._crossed_threshold(prior, current, milestone):
                continue
            results.append(
                MilestoneAchievement(
                    player_id=0,
                    player_name=team,
                    milestone=milestone,
                    current_value=current,
                    achieved=True,
                    achieved_date=date,
                    game_id=None,
                    season=season,
                    team=team,
                )
            )
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
            row = self._career_batting_cached(player_id)
            current = float(row.get(column, 0) or 0) if row else 0.0
            game_col = CAREER_GAME_CONTRIBUTION[milestone.stat]
            prior = current - self.aggregator.get_game_contribution_batting(
                player_id, game_id, game_col
            )
        elif milestone.stat in CAREER_PITCHING_STATS:
            column = CAREER_PITCHING_STATS[milestone.stat]
            row = self._career_pitching_cached(player_id)
            current = float(row.get(column, 0) or 0) if row else 0.0
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
        row = self._batting_season_cached(player_id, season)
        if not row:
            return 0.0
        if stat == "season_h":
            return float(row.get("h") or 0)
        if stat == "season_sb":
            return float(row.get("sb") or 0)
        return float(row.get(stat.replace("season_", ""), 0) or 0)

    def _season_pitching_total(self, player_id: int, season: int, stat: str) -> float:
        row = self._pitching_season_cached(player_id, season)
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
        if scope == "team_game":
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE team = ? AND milestone_key = ? AND game_id = ?
                """,
                (item.team, item.milestone.key, item.game_id),
            ).fetchone()
        elif scope in {"team_season", "team_manual"}:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE team = ? AND milestone_key = ? AND season = ?
                """,
                (item.team, item.milestone.key, item.season),
            ).fetchone()
        elif scope == "career":
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

    @staticmethod
    def _team_won_game(team: str, game: dict[str, Any]) -> bool:
        if game.get("home_team") == team:
            return int(game.get("home_score") or 0) > int(game.get("away_score") or 0)
        if game.get("away_team") == team:
            return int(game.get("away_score") or 0) > int(game.get("home_score") or 0)
        return False

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
