"""Reusable workflow status widgets for dashboard and import-center UX."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from gui.theme import TEXT_SECONDARY, hint_style
from gui.widgets.card_panel import CardPanel


WORKFLOW_STATUSES = ("complete", "needed", "warning", "running")
IMPORT_WORKFLOW_STEPS = (
    "source_check",
    "analyze_classify",
    "review_results",
    "save",
    "confirm_result",
)


@dataclass(frozen=True)
class WorkflowStep:
    """One visible workflow step with a primary action and destination link."""

    key: str
    title: str
    status: str = "needed"
    last_run: str = ""
    reason: str = ""
    action_label: str = ""
    target_label: str = ""


@dataclass(frozen=True)
class ImportResultSummary:
    """Import result summary that remains visible inside the import page."""

    outcome: str
    headline: str
    totals: dict[str, int] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)
    actions: tuple[str, ...] = ()


def status_label(status: str) -> str:
    labels = {
        "complete": tr("Complete"),
        "needed": tr("Needed"),
        "warning": tr("Warning"),
        "running": tr("Running"),
    }
    return labels.get(status, tr("Needed"))


def status_style(status: str) -> str:
    colors = {
        "complete": ("#14532d", "#dcfce7", "#86efac"),
        "needed": ("#1e3a8a", "#dbeafe", "#93c5fd"),
        "warning": ("#92400e", "#fef3c7", "#fbbf24"),
        "running": ("#5b21b6", "#ede9fe", "#c4b5fd"),
    }
    text, bg, border = colors.get(status, colors["needed"])
    return (
        f"color: {text}; background: {bg}; border: 1px solid {border};"
        " border-radius: 10px; padding: 2px 8px; font-weight: 600;"
    )


class WorkflowStepRow(QFrame):
    """Compact row used by workflow panels."""

    action_requested = pyqtSignal(str)
    target_requested = pyqtSignal(str)

    def __init__(self, step: WorkflowStep, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workflowStepRow")
        self.step_key = step.key

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(4)

        self.title_label = QLabel(step.title)
        self.title_label.setObjectName("workflowStepTitle")
        self.status_badge = QLabel(status_label(step.status))
        self.status_badge.setObjectName("workflowStatusBadge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last_run_label = QLabel(step.last_run or tr("Not run yet"))
        self.last_run_label.setObjectName("workflowLastRun")
        self.last_run_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.reason_label = QLabel(step.reason or tr("No issue reported."))
        self.reason_label.setObjectName("workflowReason")
        self.reason_label.setWordWrap(True)
        self.reason_label.setStyleSheet(hint_style(TEXT_SECONDARY))

        action_text = step.action_label or tr("Start")
        self.action_button = QPushButton(action_text)
        self.action_button.setObjectName("workflowActionButton")
        self.action_button.clicked.connect(lambda: self.action_requested.emit(step.key))

        target_text = step.target_label or tr("Open")
        self.target_button = QPushButton(target_text)
        self.target_button.setObjectName("workflowTargetButton")
        self.target_button.clicked.connect(lambda: self.target_requested.emit(step.key))

        layout.addWidget(self.status_badge, 0, 0, 2, 1)
        layout.addWidget(self.title_label, 0, 1)
        layout.addWidget(self.last_run_label, 0, 2)
        layout.addWidget(self.action_button, 0, 3)
        layout.addWidget(self.target_button, 0, 4)
        layout.addWidget(self.reason_label, 1, 1, 1, 4)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 1)

        self.update_step(step)

    def update_step(self, step: WorkflowStep) -> None:
        self.step_key = step.key
        self.title_label.setText(step.title)
        self.status_badge.setText(status_label(step.status))
        self.status_badge.setStyleSheet(status_style(step.status))
        self.last_run_label.setText(step.last_run or tr("Not run yet"))
        self.reason_label.setText(step.reason or tr("No issue reported."))
        self.action_button.setText(step.action_label or tr("Start"))
        self.target_button.setText(step.target_label or tr("Open"))


class WorkflowStatusPanel(CardPanel):
    """Visible step-by-step workflow status panel."""

    action_requested = pyqtSignal(str)
    target_requested = pyqtSignal(str)

    def __init__(
        self,
        title: str,
        description: str,
        steps: Iterable[WorkflowStep],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent=parent)
        self.setObjectName("workflowStatusPanel")
        self._rows: dict[str, WorkflowStepRow] = {}

        desc = QLabel(description)
        desc.setObjectName("workflowDescription")
        desc.setWordWrap(True)
        desc.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.add_widget(desc)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.add_widget(self.rows_container)
        self.set_steps(list(steps))

    def set_steps(self, steps: Iterable[WorkflowStep]) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()
        for step in steps:
            row = WorkflowStepRow(step)
            row.action_requested.connect(self.action_requested.emit)
            row.target_requested.connect(self.target_requested.emit)
            self.rows_layout.addWidget(row)
            self._rows[step.key] = row
        self.rows_layout.addStretch()

    def update_step(self, step: WorkflowStep) -> None:
        row = self._rows.get(step.key)
        if row is not None:
            row.update_step(step)

    def row_count(self) -> int:
        return len(self._rows)


class ImportResultSummaryWidget(CardPanel):
    """Persistent completion/partial-success/error result summary."""

    action_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Result Summary"), parent=parent)
        self.setObjectName("importResultSummary")
        self.headline_label = QLabel(tr("No import has run yet."))
        self.headline_label.setObjectName("importResultHeadline")
        self.headline_label.setWordWrap(True)
        self.content_layout.addWidget(self.headline_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("importResultDetails")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.content_layout.addWidget(self.detail_label)

        self.actions_row = QHBoxLayout()
        self.actions_row.addStretch()
        self.content_layout.addLayout(self.actions_row)

    def set_summary(self, summary: ImportResultSummary | None) -> None:
        while self.actions_row.count() > 1:
            item = self.actions_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if summary is None:
            self.headline_label.setText(tr("No import has run yet."))
            self.detail_label.setText(tr("Run an import to see what changed, what was skipped, and what needs review."))
            return

        self.headline_label.setText(summary.headline)
        parts = []
        if summary.totals:
            parts.append(
                tr("Processed: {items}").format(
                    items=" · ".join(f"{key} {value}" for key, value in summary.totals.items())
                )
            )
        if summary.unresolved:
            parts.append(
                tr("Needs review: {items}").format(
                    items=" · ".join(f"{key} {value}" for key, value in summary.unresolved.items())
                )
            )
        self.detail_label.setText("\n".join(parts) if parts else tr("No detail counts available."))
        for action in summary.actions:
            button = QPushButton(action)
            button.setObjectName("importResultActionButton")
            button.clicked.connect(lambda _checked=False, name=action: self.action_requested.emit(name))
            self.actions_row.insertWidget(self.actions_row.count() - 1, button)


class ImportWorkflowCard(CardPanel):
    """Import option card with a shared five-step status model."""

    action_requested = pyqtSignal(str, str)

    def __init__(
        self,
        key: str,
        title: str,
        description: str,
        source_hint: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent=parent)
        self.setObjectName(f"importWorkflowCard_{key}")
        self.key = key

        desc = QLabel(description)
        desc.setWordWrap(True)
        self.content_layout.addWidget(desc)

        hint = QLabel(source_hint)
        hint.setObjectName("importSourceHint")
        hint.setStyleSheet(hint_style(TEXT_SECONDARY))
        hint.setWordWrap(True)
        self.content_layout.addWidget(hint)

        self.status_panel = WorkflowStatusPanel(
            tr("Workflow"),
            tr("Each import keeps the same five stages so partial success and errors are traceable."),
            self.default_steps(),
        )
        self.status_panel.action_requested.connect(
            lambda step_key: self.action_requested.emit(self.key, step_key)
        )
        self.status_panel.target_requested.connect(
            lambda step_key: self.action_requested.emit(self.key, f"open:{step_key}")
        )
        self.content_layout.addWidget(self.status_panel)

    def default_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep("source_check", tr("Check source files"), "needed", reason=tr("Confirm the files are present before parsing."), action_label=tr("Check"), target_label=tr("Source")),
            WorkflowStep("analyze_classify", tr("Analyze and classify"), "needed", reason=tr("Parse files and group candidate records."), action_label=tr("Analyze"), target_label=tr("Details")),
            WorkflowStep("review_results", tr("Review differences or extracted records"), "needed", reason=tr("Preview what will be saved and what needs review."), action_label=tr("Review"), target_label=tr("Preview")),
            WorkflowStep("save", tr("Save approved changes"), "needed", reason=tr("Apply reviewed changes to the local database."), action_label=tr("Save"), target_label=tr("Records")),
            WorkflowStep("confirm_result", tr("Confirm result and unresolved items"), "needed", reason=tr("Keep completion, partial success, and errors visible on this page."), action_label=tr("Confirm"), target_label=tr("Issues")),
        ]

