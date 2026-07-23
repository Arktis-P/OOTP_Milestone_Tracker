"""Import result error-detail banner and dialog helpers."""

from __future__ import annotations

import sys

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from core.stats.models import BatchImportResult, ImportResult
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.import_errors_dialog import (
    ImportErrorsDialog,
    import_errors_to_clipboard_text,
)
from gui.widgets.import_result import show_import_result_banner
from gui.workers.import_worker import ImportFinishedPayload


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _payload(errors: list[ImportResult]) -> ImportFinishedPayload:
    batch = BatchImportResult(imported=2, errors=errors)
    return ImportFinishedPayload(
        batch=batch,
        milestones=[],
        milestones_recorded=0,
    )


def _action_buttons(banner: ErrorBanner):
    return [
        banner._actions_row.itemAt(index).widget()
        for index in range(banner._actions_row.count())
        if banner._actions_row.itemAt(index).widget() is not None
    ]


def test_error_banner_has_no_error_action_when_count_is_zero(qapp) -> None:
    banner = ErrorBanner()

    show_import_result_banner(
        banner,
        _payload([]),
        on_view_milestones=lambda: None,
        on_view_errors=lambda: None,
    )

    assert _action_buttons(banner) == []


def test_error_banner_shows_full_error_count_action(qapp) -> None:
    called: list[bool] = []
    banner = ErrorBanner()
    errors = [
        ImportResult(game_id=1001, error="first failure"),
        ImportResult(game_id=1002, error="second failure"),
    ]

    show_import_result_banner(
        banner,
        _payload(errors),
        on_view_milestones=lambda: None,
        on_view_errors=lambda: called.append(True),
    )

    buttons = _action_buttons(banner)
    assert len(buttons) == 1
    assert buttons[0].text() == tr("View Errors ({count})").format(count=2)

    buttons[0].click()
    assert called == [True]


def test_import_errors_clipboard_text_includes_all_errors() -> None:
    text = import_errors_to_clipboard_text(
        [
            ImportResult(game_id=1001, error="first failure"),
            ImportResult(game_id=0, error="missing game id"),
            ImportResult(game_id=1003, error=None),
        ]
    )

    assert text.splitlines() == [
        "1001\tfirst failure",
        f"{tr('Unknown')}\tmissing game id",
        f"1003\t{tr('Unknown error')}",
    ]


def test_import_errors_dialog_lists_all_errors_and_copies_selected(qapp) -> None:
    dialog = ImportErrorsDialog(
        [
            ImportResult(game_id=1001, error="first failure"),
            ImportResult(game_id=1002, error="second failure"),
        ]
    )

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 1).text() == "1001"
    assert dialog.table.item(0, 2).text() == "first failure"
    assert dialog.table.item(1, 1).text() == "1002"
    assert dialog.table.item(1, 2).text() == "second failure"

    dialog.table.selectRow(1)
    dialog.copy_selected()

    assert QApplication.clipboard().text() == "1002\tsecond failure"
