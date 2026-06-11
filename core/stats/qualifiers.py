"""Minimum qualification thresholds for ratio-based milestones."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RatioQualifiers:
    batting_ab_per_game: float = 3.1
    pitching_ip_per_game: float = 1.0


def get_batting_qualifier(
    season_games_total: int, qualifiers: RatioQualifiers | None = None
) -> int:
    ab_per_game = (qualifiers or RatioQualifiers()).batting_ab_per_game
    return round(season_games_total * ab_per_game)


def get_pitching_qualifier(
    season_games_total: int, qualifiers: RatioQualifiers | None = None
) -> int:
    ip_per_game = (qualifiers or RatioQualifiers()).pitching_ip_per_game
    return round(season_games_total * ip_per_game)


def get_pitching_qualifier_outs(
    season_games_total: int, qualifiers: RatioQualifiers | None = None
) -> int:
    from core.stats.ip_utils import ip_to_outs

    ip_str = f"{get_pitching_qualifier(season_games_total, qualifiers)}.0"
    return ip_to_outs(ip_str)
