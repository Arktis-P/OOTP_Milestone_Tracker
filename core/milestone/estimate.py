"""Pure, explainable milestone pace and attainability estimation.

Computes a season-full pace (primary basis) and a recent-N-distinct-game pace
(secondary basis) from existing season totals and per-game logs. Deliberately
avoids probability-like precision (no percentages/likelihoods): every number
here is a deterministic rate x games-remaining projection, always paired with
its sample size so the basis is explainable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.i18n import tr
from core.milestone.stat_maps import RATIO_BATTING_STATS, RATIO_PITCHING_STATS
from core.stats.ip_utils import outs_to_ip_float

RECENT_GAMES_WINDOW = 30

REASON_NO_DATA = "no_data"
REASON_UNSUPPORTED = "unsupported"

# career stat key -> column on the aggregator's season totals row
BATTING_SEASON_COLUMN: dict[str, str] = {
    "career_g": "games_played",
    "career_h": "h",
    "career_hr": "hr",
    "career_rbi": "rbi",
    "career_r": "r",
    "career_sb": "sb",
    "career_bb": "bb",
    "career_k_bat": "k",
}

# career stat key -> column on a single get_player_batting_game_logs row
BATTING_GAME_LOG_COLUMN: dict[str, str] = {
    "career_h": "h",
    "career_hr": "hr",
    "career_rbi": "rbi",
    "career_r": "r",
    "career_sb": "sb",
    "career_bb": "bb",
    "career_k_bat": "k",
}

# career stat key -> column on the aggregator's season pitching totals row
PITCHING_SEASON_COLUMN: dict[str, str] = {
    "career_g_pit": "games",
    "career_gs": "gs",
    "career_wins": "w",
    "career_k_pit": "k",
    "career_saves": "sv",
    "career_holds": "holds",
    "career_ip": "ip",
}

# career stat key -> column on a single get_player_pitching_game_logs row
PITCHING_GAME_LOG_COLUMN: dict[str, str] = {
    "career_gs": "is_starter",
    "career_wins": "win",
    "career_k_pit": "k",
    "career_saves": "save",
    "career_holds": "hold",
}


def batting_season_column(stat_key: str) -> str | None:
    """DB column on a season batting totals row for a given career stat, if supported."""
    return BATTING_SEASON_COLUMN.get(stat_key)


def pitching_season_column(stat_key: str) -> str | None:
    """DB column on a season pitching totals row for a given career stat, if supported."""
    return PITCHING_SEASON_COLUMN.get(stat_key)


def batting_recent_values(stat_key: str, game_logs: Sequence[dict]) -> list[float] | None:
    """Per-game contributions toward ``stat_key`` from batting game log rows.

    Returns ``None`` when this stat has no per-game basis (games_played and
    doubles/triples-adjacent unmapped stats).
    """
    if stat_key == "career_g":
        return [1.0] * len(game_logs)
    col = BATTING_GAME_LOG_COLUMN.get(stat_key)
    if col is None:
        return None
    return [float(row.get(col, 0) or 0) for row in game_logs]


def pitching_recent_values(stat_key: str, game_logs: Sequence[dict]) -> list[float] | None:
    """Per-game contributions toward ``stat_key`` from pitching game log rows.

    Returns ``None`` when this stat has no per-game basis available from the
    existing game log columns.
    """
    if stat_key == "career_g_pit":
        return [1.0] * len(game_logs)
    if stat_key == "career_ip":
        return [outs_to_ip_float(int(row.get("ip_outs", 0) or 0)) for row in game_logs]
    col = PITCHING_GAME_LOG_COLUMN.get(stat_key)
    if col is None:
        return None
    return [float(row.get(col, 0) or 0) for row in game_logs]


def is_stat_supported(stat_key: str, direction: str, category: str) -> bool:
    """True when a stat/direction combination has a defined pace basis at all."""
    if direction == "lower":
        return False
    if stat_key in RATIO_BATTING_STATS or stat_key in RATIO_PITCHING_STATS:
        return False
    if category == "batting":
        return stat_key in BATTING_SEASON_COLUMN
    return stat_key in PITCHING_SEASON_COLUMN


@dataclass(frozen=True)
class PaceEstimate:
    """Explainable pace-based projection toward a remaining stat target."""

    available: bool
    reason: str = ""
    remaining: float = 0.0
    games_played_season: int = 0
    season_games_total: int = 0
    games_remaining: int = 0
    season_pace: float | None = None
    projected_add_season: float | None = None
    possible_season: bool | None = None
    recent_games: int = 0
    recent_pace: float | None = None
    projected_add_recent: float | None = None
    possible_recent: bool | None = None
    games_to_target: float | None = None


def estimate_pace(
    *,
    current_value: float,
    games_played_season: int,
    season_games_total: int,
    remaining: float,
    recent_game_values: Sequence[float] = (),
    direction: str = "higher",
    is_ratio: bool = False,
) -> PaceEstimate:
    """Estimate season-end pace and attainability from existing totals/logs.

    ``recent_game_values`` are per-game contributions toward the stat for
    distinct regular-season games, ordered oldest-to-newest; only the most
    recent ``RECENT_GAMES_WINDOW`` are used as the secondary basis.
    """
    if direction == "lower" or is_ratio:
        return PaceEstimate(available=False, reason=REASON_UNSUPPORTED, remaining=remaining)
    if games_played_season <= 0:
        return PaceEstimate(available=False, reason=REASON_NO_DATA, remaining=remaining)

    games_remaining = max(season_games_total - games_played_season, 0)
    season_pace = current_value / games_played_season
    projected_add_season = season_pace * games_remaining
    possible_season = projected_add_season >= remaining if remaining > 0 else True
    games_to_target = (remaining / season_pace) if season_pace > 0 else None

    recent_window = list(recent_game_values)[-RECENT_GAMES_WINDOW:]
    recent_games = len(recent_window)
    recent_pace: float | None = None
    projected_add_recent: float | None = None
    possible_recent: bool | None = None
    if recent_games:
        recent_pace = sum(recent_window) / recent_games
        projected_add_recent = recent_pace * games_remaining
        possible_recent = projected_add_recent >= remaining if remaining > 0 else True

    return PaceEstimate(
        available=True,
        remaining=remaining,
        games_played_season=games_played_season,
        season_games_total=season_games_total,
        games_remaining=games_remaining,
        season_pace=season_pace,
        projected_add_season=projected_add_season,
        possible_season=possible_season,
        recent_games=recent_games,
        recent_pace=recent_pace,
        projected_add_recent=projected_add_recent,
        possible_recent=possible_recent,
        games_to_target=games_to_target,
    )


# ── Persistence-safe encoding (same TEXT column, richer content) ───────────

_TAG_UNAVAILABLE = "unavailable"
_TAG_ESTIMATE = "estimate"


def encode_pace_estimate(estimate: PaceEstimate) -> str:
    """Serialize a PaceEstimate to a compact pipe-delimited string."""
    if not estimate.available:
        return f"{_TAG_UNAVAILABLE}|{estimate.reason}"
    return "|".join(
        [
            _TAG_ESTIMATE,
            f"{estimate.remaining:.4f}",
            str(estimate.games_played_season),
            str(estimate.season_games_total),
            f"{estimate.season_pace:.6f}",
            f"{estimate.projected_add_season:.4f}",
            "1" if estimate.possible_season else "0",
            str(estimate.recent_games),
            "" if estimate.recent_pace is None else f"{estimate.recent_pace:.6f}",
            "" if estimate.projected_add_recent is None else f"{estimate.projected_add_recent:.4f}",
            "" if estimate.possible_recent is None else ("1" if estimate.possible_recent else "0"),
            "" if estimate.games_to_target is None else f"{estimate.games_to_target:.4f}",
        ]
    )


def decode_pace_estimate(text: str) -> PaceEstimate | None:
    """Parse a string produced by :func:`encode_pace_estimate`.

    Returns ``None`` for empty/unrecognized text (including legacy formats
    predating this module) so callers can fall back gracefully.
    """
    if not text:
        return None
    parts = text.split("|")
    if parts[0] == _TAG_UNAVAILABLE and len(parts) >= 2:
        return PaceEstimate(available=False, reason=parts[1])
    if parts[0] != _TAG_ESTIMATE or len(parts) < 12:
        return None
    try:
        return PaceEstimate(
            available=True,
            remaining=float(parts[1]),
            games_played_season=int(parts[2]),
            season_games_total=int(parts[3]),
            games_remaining=max(int(parts[3]) - int(parts[2]), 0),
            season_pace=float(parts[4]),
            projected_add_season=float(parts[5]),
            possible_season=parts[6] == "1",
            recent_games=int(parts[7]),
            recent_pace=float(parts[8]) if parts[8] else None,
            projected_add_recent=float(parts[9]) if parts[9] else None,
            possible_recent=(parts[10] == "1") if parts[10] else None,
            games_to_target=float(parts[11]) if parts[11] else None,
        )
    except (ValueError, IndexError):
        return None


# ── Display rendering ───────────────────────────────────────────────────────


def _fmt(value: float) -> str:
    return f"{value:,.0f}"


def _fmt_rate(value: float) -> str:
    return f"{value:.2f}"


def render_pace_summary(estimate: PaceEstimate | None) -> str:
    """Short, compact text for a table cell."""
    if estimate is None:
        return ""
    if not estimate.available:
        if estimate.reason == REASON_UNSUPPORTED:
            return tr("Rate stat: pace unavailable")
        return tr("No games yet")
    sample = tr("{games}G").format(games=estimate.games_played_season)
    if estimate.possible_season:
        return tr("On pace (+{amount}, {sample})").format(
            amount=_fmt(estimate.projected_add_season or 0.0), sample=sample
        )
    after = max(estimate.remaining - (estimate.projected_add_season or 0.0), 0)
    return tr("Off pace (+{amount}, {after} short, {sample})").format(
        amount=_fmt(estimate.projected_add_season or 0.0), after=_fmt(after), sample=sample
    )


def render_pace_basis(estimate: PaceEstimate | None) -> str:
    """Full explanation for a tooltip: sample sizes and both pace bases."""
    if estimate is None:
        return tr("No estimate available.")
    if not estimate.available:
        if estimate.reason == REASON_UNSUPPORTED:
            return tr(
                "This stat is a rate (not a count) or lower-is-better, "
                "so a games-pace estimate isn't meaningful."
            )
        return tr("No regular-season games logged yet this season.")

    lines = [
        tr("Season pace: {rate}/game over {games} games this season (primary basis).").format(
            rate=_fmt_rate(estimate.season_pace or 0.0), games=estimate.games_played_season
        )
    ]
    if estimate.recent_pace is not None:
        lines.append(
            tr("Recent pace: {rate}/game over the last {games} distinct games (secondary basis).").format(
                rate=_fmt_rate(estimate.recent_pace), games=estimate.recent_games
            )
        )
    else:
        lines.append(tr("Recent pace: unavailable (no recent game log)."))
    lines.append(
        tr("Projected rest-of-season addition: +{amount} ({remaining_games} games left).").format(
            amount=_fmt(estimate.projected_add_season or 0.0), remaining_games=estimate.games_remaining
        )
    )
    if estimate.games_to_target is not None:
        lines.append(
            tr("At the season pace, closing the remaining {remaining} would take about {games:.0f} games.").format(
                remaining=_fmt(estimate.remaining), games=estimate.games_to_target
            )
        )
    return "\n".join(lines)
