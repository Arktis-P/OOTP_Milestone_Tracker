"""Derives app "ready to use" state from existing settings/DB — no new storage."""

from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_manager import AppSettings
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter
from core.import_workflow import (
    WORKFLOW_BASELINE_HISTORY,
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    WORKFLOW_SEASON_FINALIZE,
    ImportWorkflowState,
    ensure_import_workflow_schema,
    load_all_import_workflow_states,
)


@dataclass
class ReadinessItem:
    key: str
    done: bool
    title: str
    detail: str


@dataclass
class DashboardImportState:
    key: str
    title: str
    workflow: ImportWorkflowState
    actionable: bool
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


def get_dashboard_import_states(
    settings: AppSettings, aggregator: Aggregator
) -> list[DashboardImportState]:
    """Return persisted workflow state for the dashboard/import center.

    This keeps the older ``settings.import_state['last_import_at']`` value as a
    legacy display fallback for latest boxscores while no workflow row exists.
    """

    if aggregator.is_closed:
        states = {
            workflow_id: ImportWorkflowState(workflow_id=workflow_id)
            for workflow_id in (
                WORKFLOW_LATEST_BOXSCORES,
                WORKFLOW_NEWS_MESSAGES,
                WORKFLOW_BASELINE_HISTORY,
                WORKFLOW_SEASON_FINALIZE,
            )
        }
    else:
        ensure_import_workflow_schema(aggregator.conn)
        states = load_all_import_workflow_states(aggregator.conn)
        legacy_last_import = (settings.import_state or {}).get("last_import_at", "")
        latest = states[WORKFLOW_LATEST_BOXSCORES]
        if legacy_last_import and latest.started_at is None:
            states[WORKFLOW_LATEST_BOXSCORES] = ImportWorkflowState(
                workflow_id=WORKFLOW_LATEST_BOXSCORES,
                current_step="confirm_result",
                outcome="completed",
                totals=dict(latest.totals),
                unresolved=dict(latest.unresolved),
                started_at=legacy_last_import,
                completed_at=legacy_last_import,
                message=tr("Legacy boxscore import timestamp restored."),
            )

    return [
        DashboardImportState(
            key=WORKFLOW_LATEST_BOXSCORES,
            title=tr("Latest boxscores"),
            workflow=states[WORKFLOW_LATEST_BOXSCORES],
            actionable=bool(settings.boxscore_dir),
            detail=_workflow_detail(states[WORKFLOW_LATEST_BOXSCORES]),
        ),
        DashboardImportState(
            key=WORKFLOW_NEWS_MESSAGES,
            title=tr("News messages"),
            workflow=states[WORKFLOW_NEWS_MESSAGES],
            actionable=bool(getattr(settings, "active_save_path", "")),
            detail=_workflow_detail(states[WORKFLOW_NEWS_MESSAGES]),
        ),
        DashboardImportState(
            key=WORKFLOW_BASELINE_HISTORY,
            title=tr("Baseline history"),
            workflow=states[WORKFLOW_BASELINE_HISTORY],
            actionable=bool(settings.initial_stats_dir),
            detail=_workflow_detail(states[WORKFLOW_BASELINE_HISTORY]),
        ),
        DashboardImportState(
            key=WORKFLOW_SEASON_FINALIZE,
            title=tr("Season finalize"),
            workflow=states[WORKFLOW_SEASON_FINALIZE],
            actionable=not aggregator.is_closed,
            detail=_workflow_detail(states[WORKFLOW_SEASON_FINALIZE]),
        ),
    ]


def _workflow_detail(state: ImportWorkflowState) -> str:
    if state.message:
        return state.message
    if state.outcome == "completed":
        return tr("Completed")
    if state.outcome == "partial_success":
        return tr("Partial success")
    if state.outcome == "failed":
        return tr("Failed")
    if state.outcome == "cancelled":
        return tr("Cancelled")
    if state.started_at:
        return tr("In progress")
    return tr("Not run yet")


def is_app_ready(settings: AppSettings, aggregator: Aggregator) -> bool:
    return all(item.done for item in get_readiness_items(settings, aggregator))
