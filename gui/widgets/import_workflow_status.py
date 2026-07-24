"""Reusable workflow status widgets for dashboard and import-center UX."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Iterable

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
    """Import result summary that remains visible inside the import page.

    ``actions`` is a tuple of ``(route_key, label)`` pairs. ``route_key`` is a
    stable identifier (e.g. ``"view_records"``, ``"check_errors"``) a future
    caller can switch on to route to a specific screen/filter; ``label`` is
    the translated button text.
    """

    outcome: str
    headline: str
    totals: dict[str, int] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)
    actions: tuple[tuple[str, str], ...] = ()


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
            if isinstance(action, tuple):
                route_key, label = action
            else:
                label = str(action)
                route_key = label
            button = QPushButton(label)
            button.setObjectName("importResultActionButton")
            button.clicked.connect(lambda _checked=False, route=route_key: self.action_requested.emit(route))
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

        self.status_panel = ImportWorkflowStatePanel(
            key,
            tr("Workflow"),
            description=tr(
                "Each import keeps the same five stages so partial success and errors are traceable."
            ),
        )
        self.status_panel.action_requested.connect(
            lambda _workflow_id, step_key: self.action_requested.emit(self.key, step_key)
        )
        self.status_panel.target_requested.connect(
            lambda _workflow_id, route: self.action_requested.emit(self.key, route)
        )
        self.content_layout.addWidget(self.status_panel)

    def set_state(self, state: Any) -> None:
        self.status_panel.set_state(state)

    def default_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep("source_check", tr("Check source files"), "needed", reason=tr("Confirm the files are present before parsing."), action_label=tr("Check"), target_label=tr("Source")),
            WorkflowStep("analyze_classify", tr("Analyze and classify"), "needed", reason=tr("Parse files and group candidate records."), action_label=tr("Analyze"), target_label=tr("Details")),
            WorkflowStep("review_results", tr("Review differences or extracted records"), "needed", reason=tr("Preview what will be saved and what needs review."), action_label=tr("Review"), target_label=tr("Preview")),
            WorkflowStep("save", tr("Save approved changes"), "needed", reason=tr("Apply reviewed changes to the local database."), action_label=tr("Save"), target_label=tr("Records")),
            WorkflowStep("confirm_result", tr("Confirm result and unresolved items"), "needed", reason=tr("Keep completion, partial success, and errors visible on this page."), action_label=tr("Confirm"), target_label=tr("Issues")),
        ]


_UNSET = object()


def _state_field(source: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a mapping/dataclass/object state, robustly.

    Accepts anything that carries the shared import-workflow state contract
    (``core.import_workflow.ImportWorkflowState`` or a plain dict/SimpleNamespace)
    without importing core, so this widget stays UI-only and testable alone.
    """
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def stage_action_label(step: str) -> str:
    labels = {
        "source_check": tr("Check"),
        "analyze_classify": tr("Analyze"),
        "review_results": tr("Review"),
        "save": tr("Save"),
        "confirm_result": tr("Confirm"),
    }
    return labels.get(step, step)


def stage_display_name(step: str) -> str:
    labels = {
        "source_check": tr("Check source"),
        "analyze_classify": tr("Analyze & classify"),
        "review_results": tr("Review results"),
        "save": tr("Save changes"),
        "confirm_result": tr("Confirm result"),
    }
    return labels.get(step, step)


def outcome_display_name(outcome: str | None) -> str:
    labels = {
        "completed": tr("Completed"),
        "partial_success": tr("Partial success"),
        "failed": tr("Failed"),
        "cancelled": tr("Cancelled"),
    }
    if outcome is None:
        return tr("In progress")
    return labels.get(outcome, outcome)


def outcome_status_key(outcome: str | None) -> str:
    mapping = {
        "completed": "complete",
        "partial_success": "warning",
        "failed": "warning",
        "cancelled": "needed",
    }
    if outcome is None:
        return "running"
    return mapping.get(outcome, "needed")


def stage_action_enabled(step: str, current_step: str, outcome: str | None) -> bool:
    """Gate a stage action button by prerequisite stage and terminal outcome.

    A step is only actionable once the workflow has reached it (its index is
    at or before the current step's index), which is what stops "analyze"
    from firing before "source check" and "save" from firing before
    "review results" have been reached. Once the workflow has a terminal
    outcome, only ``confirm_result`` (viewing/acknowledging the result)
    remains enabled.
    """
    try:
        step_index = IMPORT_WORKFLOW_STEPS.index(step)
    except ValueError:
        return False
    try:
        current_index = IMPORT_WORKFLOW_STEPS.index(current_step)
    except ValueError:
        current_index = 0
    if step_index > current_index:
        return False
    if outcome is not None and step != "confirm_result":
        return False
    return True


class ImportWorkflowStatePanel(CardPanel):
    """Reusable panel that renders the shared import-workflow state contract.

    Binds to a single ``workflow_id`` and displays ``current_step``,
    ``outcome``, ``totals`` (plus ``unresolved``/``message`` when present),
    fed via :meth:`set_state`/:meth:`update_state` from any mapping,
    dataclass, or object exposing those fields (e.g.
    ``core.import_workflow.ImportWorkflowState``). Stage buttons emit the
    stable :attr:`action_requested` signal instead of calling into core
    directly, so callers own how each action id is routed.

    ``step_labels``/``step_targets`` let a caller give each of the five
    stage buttons and the single "open" link workflow-specific text (e.g.
    "Run import" for the boxscore workflow vs. "Save approved items" for
    news messages) instead of the generic Check/Analyze/Review/Save/Confirm
    labels, so different import workflows do not present identical buttons.
    Pass updated maps to :meth:`apply_state` (e.g. when the terminal outcome
    changes what "confirm result" should say/open) to refresh immediately.
    """

    action_requested = pyqtSignal(str, str)
    target_requested = pyqtSignal(str, str)

    def __init__(
        self,
        workflow_id: str,
        title: str = "",
        parent: QWidget | None = None,
        *,
        description: str = "",
        source_hint: str = "",
        step_labels: Mapping[str, str] | None = None,
        step_targets: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(title or tr("Workflow status"), parent=parent)
        self.setObjectName(f"importWorkflowStatePanel_{workflow_id}")
        self.workflow_id = workflow_id
        self.key = workflow_id
        self.status_panel = self
        self._step_labels: dict[str, str] = dict(step_labels or {})
        self._step_targets: dict[str, tuple[str, str]] = dict(step_targets or {})
        self._open_route = ""

        self._state: dict[str, Any] = {
            "workflow_id": workflow_id,
            "current_step": IMPORT_WORKFLOW_STEPS[0],
            "outcome": None,
            "totals": {},
            "unresolved": {},
            "message": "",
        }

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            self.add_widget(desc_label)
        if source_hint:
            hint_label = QLabel(source_hint)
            hint_label.setObjectName("importSourceHint")
            hint_label.setStyleSheet(hint_style(TEXT_SECONDARY))
            hint_label.setWordWrap(True)
            self.add_widget(hint_label)

        header_row = QHBoxLayout()
        self.stage_badge = QLabel()
        self.stage_badge.setObjectName("workflowStateStageBadge")
        self.outcome_badge = QLabel()
        self.outcome_badge.setObjectName("workflowStateOutcomeBadge")
        self.open_button = QPushButton(tr("Open"))
        self.open_button.setObjectName("workflowStateOpenButton")
        self.open_button.clicked.connect(self._on_open_clicked)
        header_row.addWidget(self.stage_badge)
        header_row.addWidget(self.outcome_badge)
        header_row.addStretch()
        header_row.addWidget(self.open_button)
        self.add_layout(header_row)

        self.totals_label = QLabel()
        self.totals_label.setObjectName("workflowStateTotals")
        self.totals_label.setWordWrap(True)
        self.totals_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.add_widget(self.totals_label)

        self.unresolved_label = QLabel()
        self.unresolved_label.setObjectName("workflowStateUnresolved")
        self.unresolved_label.setWordWrap(True)
        self.unresolved_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.add_widget(self.unresolved_label)

        self.message_label = QLabel()
        self.message_label.setObjectName("workflowStateMessage")
        self.message_label.setWordWrap(True)
        self.add_widget(self.message_label)

        buttons_row = QHBoxLayout()
        self._buttons: dict[str, QPushButton] = {}
        for step in IMPORT_WORKFLOW_STEPS:
            button = QPushButton(stage_action_label(step))
            button.setObjectName(f"workflowStateAction_{step}")
            button.clicked.connect(lambda _checked=False, step_key=step: self._on_action_clicked(step_key))
            self._buttons[step] = button
            buttons_row.addWidget(button)
        buttons_row.addStretch()
        self.add_layout(buttons_row)

        self._apply_state()

    def _on_action_clicked(self, step_key: str) -> None:
        self.action_requested.emit(self.workflow_id, step_key)

    def _on_open_clicked(self) -> None:
        current_step = self._state["current_step"]
        suffix = f":{self._open_route}" if self._open_route else ""
        self.target_requested.emit(self.workflow_id, f"open:{current_step}{suffix}")

    def set_step_labels(self, step_labels: Mapping[str, str] | None) -> None:
        """Replace per-step action button text (falls back to generic labels)."""
        self._step_labels = dict(step_labels or {})
        self._apply_state()

    def set_step_targets(self, step_targets: Mapping[str, tuple[str, str]] | None) -> None:
        """Replace per-step (open label, route) pairs for the single open link."""
        self._step_targets = dict(step_targets or {})
        self._apply_state()

    def apply_state(
        self,
        state: Any,
        *,
        step_labels: Mapping[str, str] | None = None,
        step_targets: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        """Refresh state and (optionally) per-step copy/routing in one call.

        Useful when the "confirm result" step's label/destination depends on
        the new outcome (e.g. "Check errors" vs "View records").
        """
        if step_labels is not None:
            self._step_labels = dict(step_labels)
        if step_targets is not None:
            self._step_targets = dict(step_targets)
        self.set_state(state)

    def set_state(self, state: Any) -> None:
        """Replace the panel's state wholesale from a mapping/dataclass/object.

        Missing fields fall back to safe defaults so partial state objects
        (e.g. a freshly constructed workflow with no totals yet) still render.
        """
        workflow_id = _state_field(state, "workflow_id", self.workflow_id) or self.workflow_id
        current_step = _state_field(state, "current_step", IMPORT_WORKFLOW_STEPS[0]) or IMPORT_WORKFLOW_STEPS[0]
        self._state = {
            "workflow_id": workflow_id,
            "current_step": current_step,
            "outcome": _state_field(state, "outcome", None),
            "totals": dict(_state_field(state, "totals", {}) or {}),
            "unresolved": dict(_state_field(state, "unresolved", {}) or {}),
            "message": _state_field(state, "message", "") or "",
        }
        self.workflow_id = workflow_id
        self.key = workflow_id
        self._apply_state()

    def update_state(self, state: Any = None, **fields: Any) -> None:
        """Merge partial field updates into the current state.

        Accepts an optional mapping/dataclass/object for bulk fields plus
        keyword overrides, e.g. ``panel.update_state(current_step="save")``.
        """
        merged = dict(self._state)
        for key in ("workflow_id", "current_step", "outcome", "totals", "unresolved", "message"):
            value = _state_field(state, key, _UNSET)
            if value is not _UNSET:
                merged[key] = value
        merged.update(fields)
        self.set_state(merged)

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def _apply_state(self) -> None:
        current_step = self._state["current_step"]
        outcome = self._state["outcome"]
        totals = self._state["totals"]
        unresolved = self._state["unresolved"]
        message = self._state["message"]

        self.stage_badge.setText(tr("Stage: {stage}").format(stage=stage_display_name(current_step)))
        self.stage_badge.setStyleSheet(status_style("complete" if outcome is not None else "running"))

        self.outcome_badge.setText(outcome_display_name(outcome))
        self.outcome_badge.setStyleSheet(status_style(outcome_status_key(outcome)))

        if totals:
            self.totals_label.setText(
                tr("Totals: {items}").format(items=" · ".join(f"{key} {value}" for key, value in totals.items()))
            )
        else:
            self.totals_label.setText(tr("No totals recorded yet."))

        if unresolved:
            self.unresolved_label.setText(
                tr("Unresolved: {items}").format(items=" · ".join(f"{key} {value}" for key, value in unresolved.items()))
            )
            self.unresolved_label.setVisible(True)
        else:
            self.unresolved_label.setText("")
            self.unresolved_label.setVisible(False)

        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))

        for step, button in self._buttons.items():
            button.setText(self._step_labels.get(step, stage_action_label(step)))
            button.setEnabled(stage_action_enabled(step, current_step, outcome))

        target_label, route = self._step_targets.get(current_step, (tr("Open"), ""))
        self.open_button.setText(target_label)
        self._open_route = route

    def row_count(self) -> int:
        return len(self._buttons)
