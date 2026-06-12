"""v1 milestone helper logic tests."""

from __future__ import annotations

from core.milestone.composite_stats import composite_crossed, parse_hr_sb_spec
from core.milestone.definitions import MilestoneDefinition
from core.milestone.game_events import is_cycling_hit, is_grand_slam
from core.milestone.implementation import is_automatically_checkable
from core.milestone.tier_filter import filter_tiered_game_achievements


def test_cycling_hit_detection() -> None:
    assert is_cycling_hit({"h": 4, "doubles": 1, "triples": 1, "home_runs": 1})
    assert not is_cycling_hit({"h": 2, "doubles": 1, "triples": 0, "home_runs": 1})


def test_grand_slam_flag() -> None:
    assert is_grand_slam({"is_grand_slam": 1})
    assert not is_grand_slam({"is_grand_slam": 0, "home_runs": 0})


def test_hr_sb_composite_crossed() -> None:
    spec = parse_hr_sb_spec("20-20")
    assert spec is not None
    milestone = MilestoneDefinition(
        key="bat_season_hr_sb_20_20",
        label="20-20",
        stat="season_hr_sb",
        threshold=1,
        scope="season",
        category="batting",
        direction="boolean",
        threshold_spec="20-20",
    )
    assert composite_crossed(
        milestone,
        {"hr": 19, "sb": 25},
        {"hr": 20, "sb": 25},
    )
    assert not composite_crossed(
        milestone,
        {"hr": 20, "sb": 25},
        {"hr": 21, "sb": 26},
    )


def test_external_data_milestones_not_auto_checkable() -> None:
    m = MilestoneDefinition(
        key="award_mvp",
        label="MVP",
        stat="award_mvp",
        threshold=1,
        scope="season",
        category="batting",
        direction="boolean",
    )
    assert not is_automatically_checkable(m)


def test_tier_filter_keeps_highest_game_threshold() -> None:
    low = MilestoneDefinition(
        key="bat_game_hits_4",
        label="4",
        stat="h",
        threshold=4,
        scope="game",
        category="batting",
    )
    high = MilestoneDefinition(
        key="bat_game_hits_5",
        label="5",
        stat="h",
        threshold=5,
        scope="game",
        category="batting",
    )

    class Fake:
        def __init__(self, milestone, threshold_value):
            self.player_id = 1
            self.game_id = 10
            self.milestone = milestone
            self.current_value = threshold_value
            self.achieved = True

    achievements = [Fake(low, 5), Fake(high, 5)]
    filtered = filter_tiered_game_achievements(achievements)
    assert len(filtered) == 1
    assert filtered[0].milestone.threshold == 5
