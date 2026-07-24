from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from core.import_workflow import OUTCOME_CANCELLED, OUTCOME_PARTIAL_SUCCESS
from core.stats.models import BatchImportResult, ImportResult
from gui.views.dashboard_view import DashboardView
from gui.views.stats_view import StatsView
from gui.widgets.import_workflow_status import (
    IMPORT_WORKFLOW_STEPS,
    ImportWorkflowStatePanel,
    stage_action_enabled,
)
from gui.workers.import_worker import ImportFinishedPayload

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    widget = ImportWorkflowStatePanel("news_messages", "News messages")
    yield widget
    widget.deleteLater()


def test_initial_state_defaults_to_first_step_and_no_outcome(panel) -> None:
    assert panel.state["current_step"] == "source_check"
    assert panel.state["outcome"] is None
    assert panel.state["totals"] == {}
    assert panel._buttons["source_check"].isEnabled()
    assert not panel._buttons["analyze_classify"].isEnabled()
    assert not panel._buttons["save"].isEnabled()


def test_set_state_accepts_plain_dict() -> None:
    for step, current, outcome, expected in [
        ("source_check", "source_check", None, True),
        ("analyze_classify", "source_check", None, False),
        ("analyze_classify", "analyze_classify", None, True),
        ("review_results", "analyze_classify", None, False),
        ("save", "review_results", None, False),
        ("save", "save", None, True),
        ("confirm_result", "save", None, False),
        ("confirm_result", "confirm_result", None, True),
    ]:
        assert stage_action_enabled(step, current, outcome) is expected


def test_set_state_from_mapping_updates_labels_and_buttons(panel) -> None:
    panel.set_state(
        {
            "workflow_id": "news_messages",
            "current_step": "review_results",
            "outcome": None,
            "totals": {"processed": 10, "created": 4},
        }
    )

    assert panel.state["current_step"] == "review_results"
    assert panel.state["totals"] == {"processed": 10, "created": 4}
    assert panel._buttons["source_check"].isEnabled()
    assert panel._buttons["analyze_classify"].isEnabled()
    assert panel._buttons["review_results"].isEnabled()
    assert not panel._buttons["save"].isEnabled()
    assert not panel._buttons["confirm_result"].isEnabled()
    assert "10" in panel.totals_label.text()


def test_set_state_from_dataclass_like_object_reads_attributes(panel) -> None:
    state = SimpleNamespace(
        workflow_id="news_messages",
        current_step="save",
        outcome=None,
        totals={"processed": 3},
        unresolved={"errors": 1},
        message="Saving approved rows",
    )
    panel.set_state(state)

    assert panel.state["current_step"] == "save"
    assert panel.state["unresolved"] == {"errors": 1}
    assert panel.message_label.text() == "Saving approved rows"
    assert panel._buttons["save"].isEnabled()
    assert not panel._buttons["confirm_result"].isEnabled()


def test_set_state_missing_fields_fall_back_to_safe_defaults(panel) -> None:
    panel.set_state({"current_step": "analyze_classify"})

    assert panel.state["outcome"] is None
    assert panel.state["totals"] == {}
    assert panel.state["unresolved"] == {}
    assert panel.state["message"] == ""
    assert panel.workflow_id == "news_messages"


def test_update_state_merges_partial_fields(panel) -> None:
    panel.set_state({"current_step": "save", "totals": {"processed": 5}})
    panel.update_state(outcome="completed")

    assert panel.state["current_step"] == "save"
    assert panel.state["totals"] == {"processed": 5}
    assert panel.state["outcome"] == "completed"


def test_terminal_outcome_disables_all_but_confirm_result(panel) -> None:
    panel.set_state({"current_step": "confirm_result", "outcome": "completed"})

    for step in IMPORT_WORKFLOW_STEPS:
        if step == "confirm_result":
            assert panel._buttons[step].isEnabled()
        else:
            assert not panel._buttons[step].isEnabled()


def test_action_requested_emits_workflow_id_and_stable_step_action_id(panel, qapp) -> None:
    panel.set_state({"current_step": "confirm_result", "outcome": None})

    captured: list[tuple[str, str]] = []
    panel.action_requested.connect(lambda workflow_id, action_id: captured.append((workflow_id, action_id)))

    panel._buttons["source_check"].click()
    panel._buttons["analyze_classify"].click()
    panel._buttons["review_results"].click()
    panel._buttons["save"].click()
    panel._buttons["confirm_result"].click()

    assert captured == [
        ("news_messages", "source_check"),
        ("news_messages", "analyze_classify"),
        ("news_messages", "review_results"),
        ("news_messages", "save"),
        ("news_messages", "confirm_result"),
    ]


def test_action_requested_not_emitted_for_disabled_button_click(panel, qapp) -> None:
    panel.set_state({"current_step": "source_check", "outcome": None})

    captured: list[tuple[str, str]] = []
    panel.action_requested.connect(lambda workflow_id, action_id: captured.append((workflow_id, action_id)))

    panel._buttons["save"].click()

    assert captured == []


class _FakeControl:
    def __init__(self) -> None:
        self.enabled = True
        self.visible = True

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class _FakeEmitter:
    def __init__(self) -> None:
        self.emitted: list[object] = []

    def emit(self, payload: object) -> None:
        self.emitted.append(payload)


class _FakeBanner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def show_info(self, message: str, actions: object = None) -> None:
        self.calls.append(("info", message, actions))

    def show_warning(self, message: str, actions: object = None) -> None:
        self.calls.append(("warning", message, actions))

    def show_error(self, message: str, actions: object = None) -> None:
        self.calls.append(("error", message, actions))

    def show_success(self, message: str, actions: object = None) -> None:
        self.calls.append(("success", message, actions))


def _view_stub(**extra):
    base = {
        "import_button": _FakeControl(),
        "cancel_import_button": _FakeControl(),
        "progress_card": _FakeControl(),
        "progress_bar": _FakeControl(),
        "progress_label": _FakeControl(),
        "banner": _FakeBanner(),
        "import_finished": _FakeEmitter(),
        "update_status_summary": lambda: None,
        "refresh": lambda: None,
        "_reload_seasons": lambda: None,
        "reload_players": lambda: None,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def test_dashboard_import_finished_emits_structured_payload_not_message(qapp) -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(
            imported=1,
            total_scanned=2,
            errors=[ImportResult(game_id=1001, error="bad html")],
        )
    )
    view = _view_stub()

    DashboardView._on_import_finished(view, payload)

    assert view.import_finished.emitted == [payload]
    assert payload.outcome == OUTCOME_PARTIAL_SUCCESS
    assert view.banner.calls[0][0] == "warning"


def test_stats_import_finished_emits_structured_cancelled_payload(qapp) -> None:
    payload = ImportFinishedPayload.from_batch(
        BatchImportResult(imported=2, total_scanned=4),
        outcome=OUTCOME_CANCELLED,
        message="cancelled by user",
    )
    view = _view_stub()

    StatsView._on_import_finished(view, payload)

    assert view.import_finished.emitted == [payload]
    assert view.banner.calls == [("info", "cancelled by user", None)]
