"""Populate milestone record metadata (games, opponent team/player) on auto-record."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.milestone.checker import (
    CAREER_BATTING_STATS,
    CAREER_GAME_CONTRIBUTION,
    CAREER_PITCHING_STATS,
    MilestoneAchievement,
)
from core.milestone.definitions import MilestoneDefinition
from core.milestone.description_templates import (
    build_description_context,
    build_template_situational,
    fill_description,
)
from core.parser.game_log_html import GameLogHTMLParser
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_player_full_names,
)
from core.stats.aggregator import Aggregator
from core.stats.models import AtBatData, GameLogData

_HIT_RESULTS = frozenset({"Single", "Double", "Triple", "Home Run"})
_WALK_RESULTS = frozenset({"Walk", "Hit By Pitch"})


def enrich_achievement_for_record(
    aggregator: Aggregator,
    achievement: MilestoneAchievement,
    *,
    game_logs_dir: str | Path | None = None,
) -> None:
    """Fill opponent_team, opponent_player, games_at_achievement on achievement."""
    milestone = achievement.milestone
    scope = milestone.scope

    if scope in ("season", "season_ratio", "career"):
        achievement.games_at_achievement = _games_at_achievement(
            aggregator, achievement
        )
    elif scope == "team_season" and achievement.season is not None and achievement.team:
        achievement.games_at_achievement = _team_season_games(
            aggregator.conn, achievement.team, achievement.season
        )
    else:
        achievement.games_at_achievement = None

    achievement.opponent_team = _resolve_opponent_team(aggregator, achievement)

    if scope in ("season", "career"):
        achievement.opponent_player = _resolve_opponent_player(
            aggregator,
            achievement,
            game_logs_dir=game_logs_dir,
        )
    else:
        achievement.opponent_player = None

    achievement.description = _fill_achievement_description(
        aggregator, achievement, game_logs_dir=game_logs_dir
    )


_SITUATIONAL_PITCHING_STATS = frozenset({"k_pit", "career_k_pit", "season_k_pit"})


def _fill_achievement_description(
    aggregator: Aggregator,
    achievement: MilestoneAchievement,
    *,
    game_logs_dir: str | Path | None = None,
) -> str | None:
    milestone = achievement.milestone
    if not milestone.description_template or milestone.description_template == "situational":
        return None

    # Try situational (play-by-play) description when game log is available
    if game_logs_dir and achievement.game_id and _should_use_situational(milestone):
        sit = _build_situational_description(aggregator, achievement, game_logs_dir)
        if sit:
            return sit

    team = achievement.team
    if not team and achievement.game_id and achievement.player_id:
        team = _player_team_in_game(aggregator, achievement.player_id, achievement.game_id)

    context = build_description_context(
        aggregator.conn,
        game_id=achievement.game_id,
        player_id=achievement.player_id or None,
        team=team,
    )
    mapper = load_korean_name_mapper()
    full_names = load_player_full_names(aggregator)

    def name_resolver(player_id: int, english: str) -> str:
        return (
            korean_display_for_player(
                mapper,
                full_name=full_names.get(player_id),
                player_id=player_id,
            )
            or english
        )

    return fill_description(
        milestone,
        context,
        conn=aggregator.conn,
        name_resolver=name_resolver,
    )


def _should_use_situational(milestone: MilestoneDefinition) -> bool:
    if milestone.category == "batting":
        return True
    return milestone.stat in _SITUATIONAL_PITCHING_STATS


def _build_situational_description(
    aggregator: Aggregator,
    achievement: MilestoneAchievement,
    game_logs_dir: str | Path,
) -> str | None:
    game_id = achievement.game_id
    log_path = Path(game_logs_dir) / f"log_{game_id}.html"
    if not log_path.is_file():
        return None
    try:
        game_log = GameLogHTMLParser(log_path).parse()
    except Exception:
        return None
    prior = _prior_value(aggregator, achievement)
    at_bat = _find_milestone_at_bat(game_log, achievement, prior)
    if at_bat is None:
        return None
    return build_template_situational(at_bat)


def _find_milestone_at_bat(
    game_log: GameLogData,
    achievement: MilestoneAchievement,
    prior: float,
) -> AtBatData | None:
    """Return the specific at-bat where the milestone threshold was crossed."""
    milestone = achievement.milestone
    player_id = achievement.player_id
    threshold = float(milestone.threshold)

    if milestone.category == "batting":
        running = prior
        for at_bat in _iter_at_bats(game_log):
            if at_bat.batter_id != player_id:
                continue
            running += _batting_contribution(milestone.stat, at_bat)
            if _crossed(running, threshold, milestone.direction):
                return at_bat
        return None

    running = prior
    for at_bat in _iter_at_bats(game_log):
        if at_bat.pitcher_id != player_id:
            continue
        running += _pitching_contribution(milestone.stat, at_bat)
        if _crossed(running, threshold, milestone.direction):
            return at_bat
    return None


def _games_at_achievement(
    aggregator: Aggregator, achievement: MilestoneAchievement
) -> int | None:
    milestone = achievement.milestone
    player_id = achievement.player_id
    season = achievement.season

    if milestone.scope in ("season", "season_ratio") and season is not None:
        if milestone.category == "batting":
            row = aggregator.get_batting_season(player_id, season)
            return int(row["games_played"]) if row else None
        row = aggregator.get_pitching_season(player_id, season)
        return int(row["games"]) if row else None

    if milestone.scope == "career":
        if milestone.category == "batting":
            row = aggregator.get_batting_career(player_id)
            return int(row["career_games"]) if row else None
        return _pitching_career_games(aggregator, player_id)

    return None


def _pitching_career_games(aggregator: Aggregator, player_id: int) -> int | None:
    max_init = aggregator._get_max_init_season()
    init_row = aggregator.conn.execute(
        """
        SELECT COALESCE(SUM(g), 0) AS games
        FROM career_pitching_init
        WHERE player_id = ? AND season <= ?
        """,
        (player_id, max_init),
    ).fetchone()
    log_row = aggregator.conn.execute(
        """
        SELECT COUNT(DISTINCT pl.game_id) AS games
        FROM pitching_logs pl
        JOIN games gm ON gm.game_id = pl.game_id AND gm.is_mlb = 1
        WHERE pl.player_id = ?
        """,
        (player_id,),
    ).fetchone()
    total = int(init_row["games"] or 0) + int(log_row["games"] or 0)
    return total if total else None


def _team_season_games(conn: Any, team: str, season: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS games FROM games
        WHERE season = ? AND is_mlb = 1
          AND (home_team = ? OR away_team = ?)
        """,
        (season, team, team),
    ).fetchone()
    return int(row["games"]) if row else 0


def _resolve_opponent_team(
    aggregator: Aggregator, achievement: MilestoneAchievement
) -> str | None:
    game_id = achievement.game_id
    if game_id is None:
        return None

    game = aggregator.conn.execute(
        "SELECT away_team, home_team FROM games WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    if not game:
        return None

    subject_team = achievement.team
    if not subject_team:
        subject_team = _player_team_in_game(aggregator, achievement.player_id, game_id)
    if not subject_team:
        return None

    away, home = str(game["away_team"]), str(game["home_team"])
    if subject_team == away:
        return home
    if subject_team == home:
        return away
    return None


def _player_team_in_game(
    aggregator: Aggregator, player_id: int, game_id: int
) -> str | None:
    if not player_id:
        return None
    row = aggregator.conn.execute(
        """
        SELECT team FROM batting_logs WHERE player_id = ? AND game_id = ?
        UNION
        SELECT team FROM pitching_logs WHERE player_id = ? AND game_id = ?
        LIMIT 1
        """,
        (player_id, game_id, player_id, game_id),
    ).fetchone()
    return str(row["team"]) if row else None


def _resolve_opponent_player(
    aggregator: Aggregator,
    achievement: MilestoneAchievement,
    *,
    game_logs_dir: str | Path | None,
) -> str | None:
    game_id = achievement.game_id
    if game_id is None or not game_logs_dir:
        return None

    log_path = Path(game_logs_dir) / f"log_{game_id}.html"
    if not log_path.is_file():
        return _fallback_opponent_player(aggregator, achievement)

    try:
        game_log = GameLogHTMLParser(log_path).parse()
    except Exception:
        return _fallback_opponent_player(aggregator, achievement)

    prior = _prior_value(aggregator, achievement)
    opponent = _opponent_from_game_log(game_log, achievement, prior)
    if opponent:
        return opponent
    return _fallback_opponent_player(aggregator, achievement)


def _prior_value(aggregator: Aggregator, achievement: MilestoneAchievement) -> float:
    milestone = achievement.milestone
    player_id = achievement.player_id
    game_id = achievement.game_id
    current = achievement.current_value
    if game_id is None:
        return max(0.0, current - 1)

    stat = milestone.stat
    if stat in CAREER_BATTING_STATS:
        col = CAREER_GAME_CONTRIBUTION[stat]
        return current - aggregator.get_game_contribution_batting(
            player_id, game_id, col
        )
    if stat in CAREER_PITCHING_STATS and stat != "career_era":
        col = CAREER_GAME_CONTRIBUTION[stat]
        return current - aggregator.get_game_contribution_pitching(
            player_id, game_id, col
        )

    from core.milestone.checker import SEASON_COUNT_STATS

    mapping = SEASON_COUNT_STATS.get(stat)
    if not mapping:
        return max(0.0, current - 1)
    _, mode, game_col = mapping
    if mode in ("season_hr", "season_rbi"):
        prior = aggregator.get_max_prior_season_stat(
            player_id, achievement.season or 0, game_id, stat
        )
        return prior if prior is not None else max(0.0, current - 1)
    if milestone.category == "batting":
        game_row = aggregator.conn.execute(
            f"SELECT {game_col} AS v FROM batting_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        contrib = float(game_row["v"]) if game_row else 0.0
        return current - contrib
    prior = aggregator.get_max_prior_season_pitching_stat(
        player_id, achievement.season or 0, game_id, stat
    )
    return prior if prior is not None else max(0.0, current - 1)


def _opponent_from_game_log(
    game_log: GameLogData,
    achievement: MilestoneAchievement,
    prior: float,
) -> str | None:
    milestone = achievement.milestone
    player_id = achievement.player_id
    threshold = float(milestone.threshold)

    if milestone.category == "batting":
        running = prior
        for at_bat in _iter_at_bats(game_log):
            if at_bat.batter_id != player_id:
                continue
            running += _batting_contribution(milestone.stat, at_bat)
            if _crossed(running, threshold, milestone.direction):
                return at_bat.pitcher_name or None
        return None

    running = prior
    for at_bat in _iter_at_bats(game_log):
        if at_bat.pitcher_id != player_id:
            continue
        running += _pitching_contribution(milestone.stat, at_bat)
        if _crossed(running, threshold, milestone.direction):
            return at_bat.batter_name or None
    return None


def _iter_at_bats(game_log: GameLogData):
    for inning in game_log.innings:
        for at_bat in inning.at_bats:
            yield at_bat


def _batting_contribution(stat: str, at_bat: AtBatData) -> float:
    result = at_bat.result
    if stat in ("hr", "career_hr", "season_hr"):
        return 1.0 if result == "Home Run" else 0.0
    if stat in ("h", "career_h", "season_h"):
        return 1.0 if result in _HIT_RESULTS else 0.0
    if stat in ("bb", "career_bb"):
        return 1.0 if result in _WALK_RESULTS else 0.0
    if stat in ("k_bat", "career_k_bat"):
        return 1.0 if result == "Strikeout" else 0.0
    return 0.0


def _pitching_contribution(stat: str, at_bat: AtBatData) -> float:
    if stat in ("k_pit", "career_k_pit", "season_k_pit"):
        return 1.0 if at_bat.result == "Strikeout" else 0.0
    return 0.0


def _crossed(running: float, threshold: float, direction: str) -> bool:
    if direction == "lower":
        return running <= threshold
    return running >= threshold


def _fallback_opponent_player(
    aggregator: Aggregator, achievement: MilestoneAchievement
) -> str | None:
    game_id = achievement.game_id
    if game_id is None:
        return None
    milestone = achievement.milestone
    player_id = achievement.player_id
    opponent_team = achievement.opponent_team

    if milestone.category == "batting" and opponent_team:
        row = aggregator.conn.execute(
            """
            SELECT COALESCE(p.short_name, p.full_name) AS name
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.game_id = ? AND pl.team = ?
            ORDER BY pl.ip_outs DESC
            LIMIT 1
            """,
            (game_id, opponent_team),
        ).fetchone()
        return str(row["name"]) if row else None

    if milestone.category == "pitching":
        row = aggregator.conn.execute(
            """
            SELECT COALESCE(p.short_name, p.full_name) AS name
            FROM batting_logs bl
            JOIN players p ON p.player_id = bl.player_id
            JOIN games g ON g.game_id = bl.game_id AND g.is_mlb = 1
            WHERE bl.game_id = ? AND bl.team = ?
            ORDER BY bl.ab DESC
            LIMIT 1
            """,
            (game_id, opponent_team),
        ).fetchone()
        return str(row["name"]) if row else None
    return None
