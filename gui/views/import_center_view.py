"""Unified import center view.

This view is intentionally independent from ``gui.app`` wiring so it can be
tested and iterated before navigation integration: it takes no aggregator or
settings reference and instead exposes :meth:`apply_workflow_state` as the
seam a future ``gui.app`` wiring calls (with state loaded from
``core.app_state.get_dashboard_import_states``/``core.import_workflow``)
whenever a workflow's persisted state changes, and ``set_completed_summary``/
``set_partial_success_summary``/``set_error_summary`` for the page-level
result summary, matching the existing public API other callers already use.
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.i18n import tr
from gui.widgets.import_workflow_status import (
    ImportResultSummary,
    ImportResultSummaryWidget,
    ImportWorkflowStatePanel,
)

CARD_LATEST_GAMES = "latest_boxscores"
CARD_NEWS_MESSAGES = "news_messages"
CARD_BASELINE_HISTORY = "baseline_history"


def _confirm_result_presentation(
    state: Any,
    *,
    error_key: str = "errors",
    review_key: str = "review_needed",
    saved_key: str = "created",
) -> tuple[str, str, str]:
    """Pick (action label, open label, route) for the confirm_result step.

    Distinguishes routing to an error list, a review-required list, or the
    saved records themselves depending on the workflow's unresolved counts,
    so "confirm result" does not always point at the same generic screen.
    """
    unresolved = getattr(state, "unresolved", None) or (state.get("unresolved") if isinstance(state, dict) else {}) or {}
    totals = getattr(state, "totals", None) or (state.get("totals") if isinstance(state, dict) else {}) or {}
    outcome = getattr(state, "outcome", None) if not isinstance(state, dict) else state.get("outcome")

    if unresolved.get(error_key):
        return tr("Check errors"), tr("Errors"), "errors"
    if unresolved.get(review_key):
        return tr("Review needed"), tr("Review"), "review"
    if outcome in ("completed", "partial_success") and totals.get(saved_key):
        return tr("View records"), tr("Records"), "records"
    return tr("Confirm"), tr("Result"), "result"


def _latest_games_labels(state: Any) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    confirm_action, confirm_open, confirm_route = _confirm_result_presentation(
        state, error_key="errors", review_key="review_needed", saved_key="created"
    )
    labels = {
        "source_check": tr("Check folder"),
        "analyze_classify": tr("Run import"),
        "review_results": tr("Review"),
        "save": tr("Save"),
        "confirm_result": confirm_action,
    }
    targets = {
        "source_check": (tr("Source"), "source"),
        "analyze_classify": (tr("Details"), "details"),
        "review_results": (tr("Summary"), "summary"),
        "save": (tr("Records"), "records"),
        "confirm_result": (confirm_open, confirm_route),
    }
    return labels, targets


def _news_messages_labels(state: Any) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    confirm_action, confirm_open, confirm_route = _confirm_result_presentation(
        state, error_key="errors", review_key="date_missing", saved_key="created"
    )
    labels = {
        "source_check": tr("Check messages"),
        "analyze_classify": tr("Analyze"),
        "review_results": tr("Open review"),
        "save": tr("Save approved"),
        "confirm_result": confirm_action,
    }
    targets = {
        "source_check": (tr("Source"), "source"),
        "analyze_classify": (tr("Candidates"), "candidates"),
        "review_results": (tr("Review"), "review"),
        "save": (tr("Saved"), "saved"),
        "confirm_result": (confirm_open, confirm_route),
    }
    return labels, targets


def _baseline_history_labels(state: Any) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    confirm_action, confirm_open, confirm_route = _confirm_result_presentation(
        state, error_key="errors", review_key="review_needed", saved_key="created"
    )
    labels = {
        "source_check": tr("Check files & dates"),
        "analyze_classify": tr("Compare"),
        "review_results": tr("View differences"),
        "save": tr("Run import"),
        "confirm_result": confirm_action,
    }
    targets = {
        "source_check": (tr("Source"), "source"),
        "analyze_classify": (tr("Comparison"), "comparison"),
        "review_results": (tr("Differences"), "differences"),
        "save": (tr("Records"), "records"),
        "confirm_result": (confirm_open, confirm_route),
    }
    return labels, targets


LabelBuilder = Callable[[Any], tuple[dict[str, str], dict[str, tuple[str, str]]]]


class ImportCenterView(QWidget):
    """Single page for recurring, message, and baseline/history imports."""

    workflow_action_requested = pyqtSignal(str, str)
    result_action_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("importCenterView")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("importCenterScroll")
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel(tr("Record Import Center"))
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            tr(
                "Choose the import path, review the five-stage status, and keep the final "
                "completion, partial-success, or error summary visible on this page."
            )
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedLabel")
        layout.addWidget(intro)

        self._label_builders: dict[str, LabelBuilder] = {
            CARD_LATEST_GAMES: _latest_games_labels,
            CARD_NEWS_MESSAGES: _news_messages_labels,
            CARD_BASELINE_HISTORY: _baseline_history_labels,
        }

        self.latest_games_card = self._build_card(
            CARD_LATEST_GAMES,
            tr("Latest game import"),
            tr("Import recent boxscore HTML and reflect current-season games, milestones, and active streaks."),
            tr("Source: boxscore HTML files for routine repeated imports."),
        )
        self.message_card = self._build_card(
            CARD_NEWS_MESSAGES,
            tr("News message import"),
            tr("Review messages/messageN.txt extraction before saving awards, injuries, contracts, and milestones."),
            tr("Source: messages/messageN.txt with preview, save, and error handling."),
        )
        self.baseline_card = self._build_card(
            CARD_BASELINE_HISTORY,
            tr("Career and historical season import"),
            tr("Import or compare player_batting_stats.txt and player_pitching_stats.txt for initial setup and offseason refresh."),
            tr("Source: player_batting_stats.txt and player_pitching_stats.txt."),
        )

        self._cards: dict[str, ImportWorkflowStatePanel] = {
            CARD_LATEST_GAMES: self.latest_games_card,
            CARD_NEWS_MESSAGES: self.message_card,
            CARD_BASELINE_HISTORY: self.baseline_card,
        }

        for card in self._cards.values():
            card.action_requested.connect(self.workflow_action_requested.emit)
            card.target_requested.connect(self.workflow_action_requested.emit)
            layout.addWidget(card)

        self.result_summary = ImportResultSummaryWidget()
        self.result_summary.action_requested.connect(self.result_action_requested.emit)
        self.result_summary.set_summary(None)
        layout.addWidget(self.result_summary)
        layout.addStretch()

    def _build_card(self, key: str, title: str, description: str, source_hint: str) -> ImportWorkflowStatePanel:
        builder = self._label_builders[key]
        labels, targets = builder(None)
        return ImportWorkflowStatePanel(
            key,
            title,
            description=description,
            source_hint=source_hint,
            step_labels=labels,
            step_targets=targets,
        )

    def apply_workflow_state(self, card_key: str, state: Any) -> None:
        """Push an updated workflow state snapshot into one of the three cards.

        This is the seam a future ``gui.app`` wiring uses: load
        ``core.import_workflow.ImportWorkflowState`` (e.g. via
        ``core.app_state.get_dashboard_import_states``) and call this after
        every stage transition so the card's buttons, routing, and enabled
        state refresh immediately from the real workflow snapshot instead of
        staying on generic placeholders.
        """
        card_key = CARD_LATEST_GAMES if card_key == "latest_games" else card_key
        card = self._cards.get(card_key)
        if card is None:
            return
        builder = self._label_builders[card_key]
        labels, targets = builder(state)
        card.apply_state(state, step_labels=labels, step_targets=targets)

    def set_result_summary(self, summary: ImportResultSummary | None) -> None:
        self.result_summary.set_summary(summary)

    def set_completed_summary(self, totals: dict[str, int], unresolved: dict[str, int] | None = None) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="complete",
                headline=tr("Record import completed."),
                totals=totals,
                unresolved=unresolved or {},
                actions=(
                    ("view_records", tr("View records")),
                    ("review_issues", tr("Review issues")),
                    ("check_errors", tr("Check errors")),
                ),
            )
        )

    def set_partial_success_summary(self, totals: dict[str, int], unresolved: dict[str, int]) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="partial_success",
                headline=tr("Record import partially completed. Some items need review."),
                totals=totals,
                unresolved=unresolved,
                actions=(
                    ("view_records", tr("View records")),
                    ("review_issues", tr("Review issues")),
                    ("check_errors", tr("Check errors")),
                ),
            )
        )

    def set_error_summary(self, message: str, totals: dict[str, int] | None = None) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="error",
                headline=tr("Record import stopped: {message}").format(message=message),
                totals=totals or {},
                unresolved={tr("errors"): 1},
                actions=(("check_errors", tr("Check errors")),),
            )
        )
