"""Shared boxscore-import result banner (dashboard + milestone views)."""

from __future__ import annotations

from typing import Callable

from core.i18n import tr
from gui.widgets.error_banner import ErrorBanner
from gui.workers.import_worker import ImportFinishedPayload


def build_import_message(payload: ImportFinishedPayload) -> str:
    result = payload.batch
    parts = [tr("{count} games added").format(count=result.imported)]
    if payload.milestones_recorded:
        parts.append(
            tr("{count} milestones achieved").format(count=payload.milestones_recorded)
        )
    if result.skipped_non_mlb:
        parts.append(tr("{count} non-MLB skipped").format(count=result.skipped_non_mlb))
    if result.skipped_spring_training:
        parts.append(
            tr("{count} spring training skipped").format(count=result.skipped_spring_training)
        )
    if result.errors:
        parts.append(tr("{count} errors").format(count=len(result.errors)))
    return tr("Import Complete") + " · " + " · ".join(parts)


def show_import_result_banner(
    banner: ErrorBanner,
    payload: ImportFinishedPayload,
    *,
    on_view_milestones: Callable[[], None],
    on_view_error: Callable[[], None] | None = None,
) -> None:
    message = build_import_message(payload)
    actions: list[tuple[str, Callable[[], None]]] = []
    if payload.milestones:
        actions.append((tr("View New Milestones"), on_view_milestones))
    if payload.batch.errors and on_view_error:
        actions.append((tr("View First Error"), on_view_error))

    if payload.batch.errors:
        banner.show_warning(message, actions)
    elif payload.batch.imported == 0 and not payload.milestones:
        banner.show_info(message)
    else:
        banner.show_success(message, actions)
