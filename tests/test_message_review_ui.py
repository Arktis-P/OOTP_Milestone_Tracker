"""Standalone tests for the news-message review workflow."""

from __future__ import annotations

import os
from datetime import date

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QLabel

from core.milestone.manual_entry import ManualMilestoneFormData
from core.milestone.message_automation.parser import ParsedMessage
from gui.views.message_review_view import MessageReviewView
from gui.widgets.message_review_model import (
    STATUS_APPLIED,
    STATUS_APPROVED,
    STATUS_CANDIDATE,
    STATUS_DATE_NEEDED,
    STATUS_ERROR,
    STATUS_EXCLUDED,
    MessageReviewItem,
    MessageReviewModel,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _form(
    achieved_date: date | None = date(2026, 7, 24),
    *,
    player_id: int = 101,
) -> ManualMilestoneFormData:
    return ManualMilestoneFormData(
        target="player",
        achieved_date=achieved_date,  # type: ignore[arg-type]
        player_id=player_id,
        team=None,
        milestone_key="award_mvp",
        season=2026 if achieved_date else None,
        achieved_value=1,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="MVP award",
        notes="source:message1",
    )


def _parsed(
    title: str,
    *,
    forms: list[ManualMilestoneFormData] | None = None,
    excluded: bool = False,
    reason: str | None = None,
    source_id: str = "message1",
) -> ParsedMessage:
    return ParsedMessage(
        category="award_mvp",
        title=title,
        excluded=excluded,
        exclusion_reason=reason,
        forms=forms or [],
        source_id=source_id,
        player_names={101: "Alpha Hitter"},
    )


def test_review_model_summarizes_candidates_excluded_dates_and_errors() -> None:
    model = MessageReviewModel(
        [
            MessageReviewItem(_parsed("Candidate", forms=[_form()])),
            MessageReviewItem(_parsed("Excluded", excluded=True, reason="tracked team not involved")),
            MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="message2")),
            MessageReviewItem(_parsed("Already applied", forms=[_form()], source_id="message3"), created_record_ids=[7]),
            MessageReviewItem(_parsed("Broken", source_id="message4"), error="parse failed"),
        ]
    )

    counts = model.summary_counts()

    assert counts["total"] == 5
    assert counts["candidates"] == 1
    assert counts["applied"] == 1
    assert counts["excluded"] == 1
    assert counts["date_needed"] == 1
    assert counts["errors"] == 1


def test_review_model_approval_exclusion_and_batch_date_assignment() -> None:
    model = MessageReviewModel(
        [
            MessageReviewItem(_parsed("Candidate", forms=[_form()])),
            MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="message2")),
        ]
    )

    assert model.approve([0]) == 1
    assert model[0].status == STATUS_APPROVED
    assert model.assign_date([1], date(2026, 8, 9)) == 1
    assert model[1].status == STATUS_CANDIDATE
    assert model[1].parsed.forms[0].achieved_date == date(2026, 8, 9)
    assert model[1].parsed.forms[0].season == 2026

    assert model.exclude([1], "not a record") == 1
    assert model[1].status == STATUS_EXCLUDED
    assert model[1].parsed.excluded is True


def test_view_does_not_call_save_callback_until_rows_are_approved(qapp) -> None:
    saved: list[list[ParsedMessage]] = []
    view = MessageReviewView(
        [MessageReviewItem(_parsed("Candidate", forms=[_form()]), raw_text="Candidate\nBody")],
        save_callback=lambda parsed: saved.append(parsed) or [11],
    )
    try:
        assert view.save_approved() is None
        assert saved == []

        view.table.selectRow(0)
        assert view.approve_selected() == 1
        assert view.model[0].status == STATUS_APPROVED
        assert view.save_approved() == [11]

        assert len(saved) == 1
        assert saved[0][0].title == "Candidate"
        assert view.model[0].status == STATUS_APPLIED
        assert view.model[0].created_record_ids == [11]
    finally:
        view.deleteLater()


def test_view_shows_required_summary_list_original_and_extracted_details(qapp) -> None:
    view = MessageReviewView(
        [
            MessageReviewItem(_parsed("Candidate", forms=[_form()]), raw_text="Candidate\nBody"),
            MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="message2"), raw_text="Missing\nBody"),
        ]
    )
    try:
        labels = "\n".join(label.text() for label in view.findChildren(QLabel))
        assert "Total 2" in labels
        assert "Date needed 1" in labels
        assert view.table.rowCount() == 2
        assert view.table.item(0, 1).text() == "Candidate"
        assert view.table.item(0, 5).text() == "1"

        view.table.selectRow(0)
        assert "Candidate\nBody" == view.raw_text.toPlainText()
        details = view.extracted_text.toPlainText()
        assert "Source: message1" in details
        assert "ManualMilestoneFormData" in details
        assert "milestone_key: award_mvp" in details
    finally:
        view.deleteLater()


def test_view_reanalysis_and_date_waiting_workflow(qapp) -> None:
    def reanalyze(item: MessageReviewItem) -> ParsedMessage:
        assert item.source_id == "message2"
        return _parsed("Reanalyzed", forms=[_form()], source_id="message2")

    view = MessageReviewView(
        [MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="message2"))],
        reanalyze_callback=reanalyze,
    )
    try:
        view.table.selectRow(0)
        assert view.model[0].status == STATUS_DATE_NEEDED
        view.date_edit.setDate(QDate(2026, 9, 10))
        assert view.assign_date_to_selected() == 1
        assert view.model[0].status == STATUS_CANDIDATE
        assert view.model[0].parsed.forms[0].achieved_date == date(2026, 9, 10)

        assert view.reanalyze_selected() == 1
        assert view.model[0].title == "Reanalyzed"
        assert view.model[0].status == STATUS_CANDIDATE
    finally:
        view.deleteLater()


def test_extracted_result_edit_updates_form_and_returns_to_candidate(qapp) -> None:
    saved: list[list[ParsedMessage]] = []
    view = MessageReviewView(
        [MessageReviewItem(_parsed("Candidate", forms=[_form()]))],
        save_callback=lambda parsed: saved.append(parsed) or [12],
    )
    try:
        view.table.selectRow(0)
        assert view.approve_selected() == 1
        assert view.model[0].status == STATUS_APPROVED

        ok = view.apply_extracted_edits(
            0,
            {
                "achieved_date": "2026-08-15",
                "player_id": "202",
                "description": "Corrected MVP description",
                "notes": "source:message1; reviewer corrected player",
            },
        )

        assert ok is True
        assert view.model[0].status == STATUS_CANDIDATE
        form = view.model[0].parsed.forms[0]
        assert form.achieved_date == date(2026, 8, 15)
        assert form.player_id == 202
        assert form.description == "Corrected MVP description"
        assert "reviewer corrected player" in form.notes
        assert view.save_approved() is None
        assert saved == []
    finally:
        view.deleteLater()


def test_invalid_extracted_result_edit_blocks_save_and_leaves_page_error(qapp) -> None:
    saved: list[list[ParsedMessage]] = []
    view = MessageReviewView(
        [MessageReviewItem(_parsed("Candidate", forms=[_form()]))],
        save_callback=lambda parsed: saved.append(parsed) or [13],
    )
    try:
        view.table.selectRow(0)
        assert view.approve_selected() == 1

        ok = view.apply_extracted_edits(0, {"achieved_date": "2026-99-99"})

        assert ok is False
        assert view.model[0].status == STATUS_ERROR
        assert "YYYY-MM-DD" in view.model[0].error
        assert "YYYY-MM-DD" in view.table.item(0, 6).text()
        assert view.save_approved() is None
        assert saved == []
    finally:
        view.deleteLater()


def test_edit_extracted_result_dialog_exposes_dataclass_fields(qapp) -> None:
    from gui.views.message_review_view import ExtractedResultEditDialog

    item = MessageReviewItem(_parsed("Candidate", forms=[_form()]))
    dialog = ExtractedResultEditDialog(item)
    try:
        values = dialog.edited_values()

        assert values["achieved_date"] == "2026-07-24"
        assert values["player_id"] == "101"
        assert values["description"] == "MVP award"
        assert values["notes"] == "source:message1"
        assert dialog.selected_form_index() == 0
    finally:
        dialog.deleteLater()
