"""Detect complete game, shutout, no-hitter, and perfect game from box score data."""

from __future__ import annotations

from core.parser.batting_notes import parse_team_batting_notes
from core.stats.models import BatterLine, BoxscoreData, GameMeta, PitcherLine


def detect_special_game(
    pitcher_line: PitcherLine,
    team_pitchers: list[PitcherLine],
    game_meta: GameMeta,
    team: str,
    data: BoxscoreData,
) -> dict[str, int]:
    """Return is_cg / is_sho / is_no_hitter / is_perfect_game flags for one pitcher."""
    is_home = team == game_meta.home_team
    opp_hits = game_meta.away_hits if is_home else game_meta.home_hits
    opp_errors = game_meta.away_errors if is_home else game_meta.home_errors
    opp_batters = data.away_batting if is_home else data.home_batting
    opp_notes = data.away_batting_notes if is_home else data.home_batting_notes

    is_cg = len(team_pitchers) == 1
    is_sho = is_cg and pitcher_line.r == 0
    is_no_hitter = is_sho and opp_hits == 0

    opp_bb = sum(batter.bb for batter in opp_batters)
    opp_hbp = sum(
        counts.hit_by_pitch
        for counts in parse_team_batting_notes(opp_notes).values()
    )
    is_perfect = is_no_hitter and opp_bb == 0 and opp_hbp == 0 and opp_errors == 0

    if is_perfect:
        is_no_hitter = True
        is_sho = True
        is_cg = True
    elif is_no_hitter:
        is_sho = True
        is_cg = True
    elif is_sho:
        is_cg = True

    return {
        "is_cg": int(is_cg),
        "is_sho": int(is_sho),
        "is_no_hitter": int(is_no_hitter),
        "is_perfect_game": int(is_perfect),
    }
