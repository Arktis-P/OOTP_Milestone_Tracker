"""Derives app "ready to use" state from existing settings/DB — no new storage."""

from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_manager import AppSettings
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter


@dataclass
class ReadinessItem:
    key: str
    done: bool
    title: str
    detail: str


def get_readiness_items(settings: AppSettings, aggregator: Aggregator) -> list[ReadinessItem]:
    items: list[ReadinessItem] = []

    league_done = bool(settings.active_save)
    items.append(
        ReadinessItem(
            key="league",
            done=league_done,
            title=tr("Active league selected"),
            detail=settings.active_save if league_done else tr("No league selected yet."),
        )
    )

    teams_done = bool(settings.tracked_teams)
    items.append(
        ReadinessItem(
            key="teams",
            done=teams_done,
            title=tr("Tracked teams configured"),
            detail=(
                ", ".join(settings.tracked_teams)
                if teams_done
                else tr("No tracked teams configured yet.")
            ),
        )
    )

    init_done = False
    init_detail = tr("Existing career/season records have not been imported yet.")
    if not aggregator.is_closed:
        importer = InitialImporter(aggregator)
        summary = importer.get_init_summary()
        init_done = bool(summary["batting_players"] or summary["pitching_players"])
        if init_done:
            init_detail = tr("Through {season} season · {batting:,} batters / {pitching:,} pitchers").format(
                season=summary["season_coverage"],
                batting=summary["batting_players"],
                pitching=summary["pitching_players"],
            )
    items.append(
        ReadinessItem(
            key="init_import",
            done=init_done,
            title=tr("Existing records imported"),
            detail=init_detail,
        )
    )

    boxscore_done = False
    boxscore_detail = tr("No boxscores have been imported yet.")
    if not aggregator.is_closed:
        games = aggregator.get_db_summary().get("games", 0)
        boxscore_done = games > 0
        if boxscore_done:
            boxscore_detail = tr("{games:,} MLB games imported").format(games=games)
    items.append(
        ReadinessItem(
            key="boxscore_import",
            done=boxscore_done,
            title=tr("Boxscores imported"),
            detail=boxscore_detail,
        )
    )

    return items


def is_app_ready(settings: AppSettings, aggregator: Aggregator) -> bool:
    return all(item.done for item in get_readiness_items(settings, aggregator))
