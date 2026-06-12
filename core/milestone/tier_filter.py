"""Keep only the highest tier game milestone per player/stat/game."""

from __future__ import annotations

from typing import Any


def filter_tiered_game_achievements(
    achievements: list[Any],
) -> list[Any]:
    """For game scope, retain only the highest threshold per player+stat+game."""
    best: dict[tuple[int, str, int | None, str], MilestoneAchievement] = {}
    passthrough: list[MilestoneAchievement] = []

    for item in achievements:
        if item.milestone.scope != "game" or item.game_id is None:
            passthrough.append(item)
            continue
        if item.milestone.direction == "boolean":
            passthrough.append(item)
            continue
        key = (
            item.player_id,
            item.milestone.stat,
            item.game_id,
            item.milestone.category,
        )
        existing = best.get(key)
        if existing is None or item.milestone.threshold > existing.milestone.threshold:
            best[key] = item

    return passthrough + list(best.values())
