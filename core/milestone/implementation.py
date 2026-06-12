"""Which v1 milestones can be checked automatically with current data sources."""

from __future__ import annotations

from core.milestone.definitions import MilestoneDefinition

# Requires league standings / awards export (not in boxscore pipeline).
EXTERNAL_DATA_STATS: frozenset[str] = frozenset(
    {
        "title_batting_champion",
        "title_hr_leader",
        "title_rbi_leader",
        "title_sb_leader",
        "title_ops_leader",
        "title_hits_leader",
        "title_runs_leader",
        "title_slg_leader",
        "title_triple_crown",
        "title_era_leader",
        "title_wins_leader",
        "title_strikeout_leader",
        "title_saves_leader",
        "title_ip_leader",
        "title_holds_leader",
        "title_win_pct_leader",
        "title_fip_leader",
        "award_all_star",
        "award_player_of_month",
        "award_silver_slugger",
        "award_gold_glove",
        "award_rookie_of_year",
        "award_mvp",
        "award_reliever_of_year",
        "award_cy_young",
        "hall_of_fame",
        "retired_number",
        "division_title",
        "wildcard_series_win",
        "division_series_win",
        "league_championship_series_win",
        "world_series_win",
    }
)

RATIO_SEASON_STATS: frozenset[str] = frozenset(
    {
        "season_avg",
        "season_obp",
        "season_slg",
        "season_ops",
        "season_era",
    }
)


def requires_external_data(milestone: MilestoneDefinition) -> bool:
    return milestone.stat in EXTERNAL_DATA_STATS


def requires_manual_entry(milestone: MilestoneDefinition) -> bool:
    return requires_external_data(milestone)


def is_ratio_season_stat(milestone: MilestoneDefinition) -> bool:
    return milestone.stat in RATIO_SEASON_STATS and milestone.scope == "season"


def manual_entry_hint(milestone: MilestoneDefinition) -> str:
    return f"「{milestone.label}」 마일스톤은 수동으로 입력해야 합니다."


def is_automatically_checkable(milestone: MilestoneDefinition) -> bool:
    if not milestone.active:
        return False
    if requires_external_data(milestone):
        return False
    if is_ratio_season_stat(milestone):
        return False
    return True
