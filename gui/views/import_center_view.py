"""Unified import center view.

This view is intentionally independent from ``gui.app`` wiring so it can be
tested and iterated before navigation integration.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.i18n import tr
from gui.widgets.import_workflow_status import (
    ImportResultSummary,
    ImportResultSummaryWidget,
    ImportWorkflowCard,
)


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

        self.latest_games_card = ImportWorkflowCard(
            "latest_games",
            tr("Latest game import"),
            tr("Import recent boxscore HTML and reflect current-season games, milestones, and active streaks."),
            tr("Source: boxscore HTML files for routine repeated imports."),
        )
        self.message_card = ImportWorkflowCard(
            "news_messages",
            tr("News message import"),
            tr("Review messages/messageN.txt extraction before saving awards, injuries, contracts, and milestones."),
            tr("Source: messages/messageN.txt with preview, save, and error handling."),
        )
        self.baseline_card = ImportWorkflowCard(
            "baseline_history",
            tr("Career and historical season import"),
            tr("Import or compare player_batting_stats.txt and player_pitching_stats.txt for initial setup and offseason refresh."),
            tr("Source: player_batting_stats.txt and player_pitching_stats.txt."),
        )

        for card in (self.latest_games_card, self.message_card, self.baseline_card):
            card.action_requested.connect(self.workflow_action_requested.emit)
            layout.addWidget(card)

        self.result_summary = ImportResultSummaryWidget()
        self.result_summary.action_requested.connect(self.result_action_requested.emit)
        self.result_summary.set_summary(None)
        layout.addWidget(self.result_summary)
        layout.addStretch()

    def set_result_summary(self, summary: ImportResultSummary | None) -> None:
        self.result_summary.set_summary(summary)

    def set_completed_summary(self, totals: dict[str, int], unresolved: dict[str, int] | None = None) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="complete",
                headline=tr("Record import completed."),
                totals=totals,
                unresolved=unresolved or {},
                actions=(tr("View records"), tr("Review issues"), tr("Check errors")),
            )
        )

    def set_partial_success_summary(self, totals: dict[str, int], unresolved: dict[str, int]) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="partial_success",
                headline=tr("Record import partially completed. Some items need review."),
                totals=totals,
                unresolved=unresolved,
                actions=(tr("View records"), tr("Review issues"), tr("Check errors")),
            )
        )

    def set_error_summary(self, message: str, totals: dict[str, int] | None = None) -> None:
        self.set_result_summary(
            ImportResultSummary(
                outcome="error",
                headline=tr("Record import stopped: {message}").format(message=message),
                totals=totals or {},
                unresolved={tr("errors"): 1},
                actions=(tr("Check errors"),),
            )
        )

