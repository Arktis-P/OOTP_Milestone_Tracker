"""Stat name to DB column / aggregation mappings for milestone checking."""

from __future__ import annotations

CAREER_BATTING_STATS: dict[str, str] = {
    "career_g": "career_games",
    "career_h": "career_h",
    "career_hr": "career_hr",
    "career_rbi": "career_rbi",
    "career_r": "career_r",
    "career_sb": "career_sb",
    "career_bb": "career_bb",
    "career_k_bat": "career_k",
}

CAREER_PITCHING_STATS: dict[str, str] = {
    "career_g_pit": "career_g_pit",
    "career_gs": "career_gs",
    "career_wins": "career_wins",
    "career_ip": "career_ip",
    "career_k_pit": "career_k",
    "career_saves": "career_saves",
    "career_holds": "career_holds",
    "career_era": "career_era",
}

CAREER_GAME_CONTRIBUTION: dict[str, str] = {
    "career_g": "g",
    "career_h": "h",
    "career_hr": "hr",
    "career_rbi": "rbi",
    "career_r": "r",
    "career_sb": "sb",
    "career_bb": "bb",
    "career_k_bat": "k_bat",
    "career_g_pit": "g_pit",
    "career_gs": "gs",
    "career_wins": "wins",
    "career_ip": "ip_outs",
    "career_k_pit": "k_pit",
    "career_saves": "saves",
    "career_holds": "hold",
}

# mode: sum = season total from logs; box = cumulative column on batting_logs row
SEASON_BATTING_STATS: dict[str, tuple[str, str]] = {
    "season_h": ("sum", "h"),
    "season_hr": ("box", "season_hr"),
    "season_rbi": ("box", "season_rbi"),
    "season_r": ("sum", "r"),
    "season_sb": ("sum", "stolen_bases"),
    "season_bb": ("sum", "bb"),
}

SEASON_PITCHING_STATS: dict[str, tuple[str, str]] = {
    "season_wins": ("sum", "wins"),
    "season_k_pit": ("sum", "k"),
    "season_saves": ("sum", "saves"),
    "season_ip": ("sum", "ip_outs"),
    "season_holds": ("box", "season_holds"),
}

SEASON_BATTING_RATIO_STATS: dict[str, str] = {
    "season_avg": "season_avg",
    "season_obp": "obp",
    "season_slg": "slg",
    "season_ops": "ops",
}

SEASON_PITCHING_RATIO_STATS: dict[str, str] = {
    "season_era": "season_era",
}

RATIO_BATTING_STATS = frozenset(SEASON_BATTING_RATIO_STATS)
RATIO_PITCHING_STATS = frozenset(SEASON_PITCHING_RATIO_STATS)

GAME_BATTING_COLUMNS: dict[str, str] = {
    "h": "h",
    "hr": "home_runs",
    "rbi": "rbi",
    "bb": "bb",
    "sb": "stolen_bases",
    "doubles": "doubles",
    "k_bat": "k",
}

GAME_PITCHING_COLUMNS: dict[str, str] = {
    "k_pit": "k",
    "ip_outs": "ip_outs",
    "cg": "is_cg",
    "sho": "is_sho",
    "no_hitter": "is_no_hitter",
    "perfect_game": "is_perfect_game",
}
