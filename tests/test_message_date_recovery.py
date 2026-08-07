from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from core.milestone.message_automation.parser import parse_message
from gui.views.message_review_view import MessageReviewView
from gui.widgets.message_review_model import (
    STATUS_CANDIDATE,
    STATUS_DATE_NEEDED,
    MessageReviewItem,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FIXTURES = Path(__file__).parent / "fixtures" / "messages"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "fixture",
    [
        "trade_simple_01.txt",
        "fa_signing_mlb_01.txt",
        "contract_extension_01.txt",
        "injury_game_01.txt",
    ],
)
def test_date_required_message_is_reparsed_into_unapproved_candidate(
    qapp, fixture: str
) -> None:
    path = FIXTURES / fixture
    raw = path.read_text(encoding="utf-8")
    parsed = parse_message(raw, tracked_teams=[], source_id=path.stem)
    item = MessageReviewItem(parsed, raw_text=raw)
    assert item.status == STATUS_DATE_NEEDED

    def reanalyze(row: MessageReviewItem):
        return parse_message(
            row.raw_text,
            tracked_teams=[],
            message_date=row.message_date,
            season_hint=2026,
            source_id=row.source_id,
        )

    view = MessageReviewView([item], reanalyze_callback=reanalyze)
    try:
        view.table.selectRow(0)
        view.date_edit.setDate(QDate(2026, 5, 1))

        assert view.assign_date_to_selected() == 1
        recovered = view.model[0]
        assert recovered.message_date == date(2026, 5, 1)
        assert recovered.status == STATUS_CANDIDATE
        assert recovered.parsed.forms
        assert not recovered.can_save()
    finally:
        view.close()

