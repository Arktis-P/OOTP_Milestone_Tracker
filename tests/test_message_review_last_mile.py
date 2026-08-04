"""Regression coverage for the message-review model's "last mile" behavior:

- an explicit ``changed_review_needed`` state (surfaced via ``notice`` +
  ``FILTER_CHANGED_REVIEW_NEEDED``, not a ``status`` value)
- filtering by ``new``, ``changed_review_needed``, ``excluded`` and ``error``
- safe bulk selection (non-actionable rows are never swept up by bulk ops)
- changed/date-missing rows cannot be approved or saved until explicitly
  reanalyzed, edited, or given a date
"""

from __future__ import annotations

from datetime import date

from core.milestone.manual_entry import ManualMilestoneFormData
from core.milestone.message_automation.parser import ParsedMessage
from gui.widgets.message_review_model import (
    FILTER_CHANGED_REVIEW_NEEDED,
    FILTER_NEW,
    NOTICE_CHANGED_SOURCE,
    STATUS_APPLIED,
    STATUS_APPROVED,
    STATUS_CANDIDATE,
    STATUS_DATE_NEEDED,
    STATUS_ERROR,
    STATUS_EXCLUDED,
    MessageReviewItem,
    MessageReviewModel,
)


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
        forms=forms if forms is not None else [_form()],
        source_id=source_id,
        player_names={101: "Alpha Hitter"},
    )


def test_changed_review_needed_is_filterable_and_counted_without_a_dedicated_status() -> None:
    changed = MessageReviewItem(_parsed("Changed", source_id="changed"))
    changed.notice = NOTICE_CHANGED_SOURCE
    plain_candidate = MessageReviewItem(_parsed("Plain", source_id="plain"))

    model = MessageReviewModel([changed, plain_candidate])

    # The row is still a normal candidate status-wise...
    assert changed.status == STATUS_CANDIDATE
    # ...but is exposed as its own bucket through the virtual filter and counts.
    assert model.filtered_indexes(FILTER_CHANGED_REVIEW_NEEDED) == [0]
    assert model.summary_counts()["changed_review_needed"] == 1


def test_new_filter_matches_candidate_status_and_excludes_other_states() -> None:
    model = MessageReviewModel(
        [
            MessageReviewItem(_parsed("Candidate", source_id="candidate")),
            MessageReviewItem(_parsed("Excluded", forms=[], excluded=True, reason="tracked team not involved", source_id="excluded")),
            MessageReviewItem(_parsed("Broken", forms=[], source_id="error"), error="parse failed"),
        ]
    )

    assert model.filtered_indexes(FILTER_NEW) == model.filtered_indexes(STATUS_CANDIDATE) == [0]
    assert model.filtered_indexes(STATUS_EXCLUDED) == [1]
    assert model.filtered_indexes(STATUS_ERROR) == [2]


def test_changed_source_item_blocks_approval_until_reanalyzed() -> None:
    item = MessageReviewItem(_parsed("Changed", source_id="changed"))
    item.notice = NOTICE_CHANGED_SOURCE
    model = MessageReviewModel([item])

    assert item.can_approve() is False
    assert model.approve([0]) == 0
    assert model[0].status == STATUS_CANDIDATE

    model.update_parsed(0, _parsed("Reanalyzed", source_id="changed"))

    assert model[0].notice == ""
    assert model[0].can_approve() is True
    assert model.approve([0]) == 1
    assert model[0].status == STATUS_APPROVED


def test_changed_source_item_blocks_approval_until_manually_edited() -> None:
    item = MessageReviewItem(_parsed("Changed", source_id="changed"))
    item.notice = NOTICE_CHANGED_SOURCE
    model = MessageReviewModel([item])

    assert model.approve([0]) == 0

    model.update_form_fields(0, 0, {"description": "Reviewer confirmed"})

    assert model[0].notice == ""
    assert model[0].status == STATUS_CANDIDATE
    assert model.approve([0]) == 1
    assert model[0].status == STATUS_APPROVED


def test_missing_date_blocks_approval_and_save_until_assigned() -> None:
    item = MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="missing"))
    model = MessageReviewModel([item])

    assert model[0].status == STATUS_DATE_NEEDED
    assert model[0].can_approve() is False
    assert model.approve([0]) == 0
    assert model[0].can_save() is False

    assert model.assign_date([0], date(2026, 8, 9)) == 1
    assert model[0].status == STATUS_CANDIDATE
    assert model.approve([0]) == 1
    assert model[0].status == STATUS_APPROVED
    assert model[0].can_save() is True
    assert model.approved_items() == [model[0]]


def test_bulk_approve_all_only_touches_actionable_rows() -> None:
    changed = MessageReviewItem(_parsed("Changed", source_id="changed"))
    changed.notice = NOTICE_CHANGED_SOURCE
    excluded = MessageReviewItem(_parsed("Excluded", forms=[], excluded=True, reason="tracked team not involved", source_id="excluded"))
    errored = MessageReviewItem(_parsed("Broken", forms=[], source_id="error"), error="parse failed")
    date_needed = MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="date"))
    applied = MessageReviewItem(_parsed("Applied", source_id="applied"), created_record_ids=[7])
    plain_candidate = MessageReviewItem(_parsed("Plain", source_id="plain"))

    model = MessageReviewModel(
        [changed, excluded, errored, date_needed, applied, plain_candidate]
    )

    assert model.approve_all_candidates() == 1

    assert model[0].status == STATUS_CANDIDATE  # changed-source row untouched
    assert model[1].status == STATUS_EXCLUDED
    assert model[2].status == STATUS_ERROR
    assert model[3].status == STATUS_DATE_NEEDED
    assert model[4].status == STATUS_APPLIED
    assert model[5].status == STATUS_APPROVED  # only the actionable row changed


def test_bulk_exclude_skips_applied_and_error_rows() -> None:
    plain_candidate = MessageReviewItem(_parsed("Plain", source_id="plain"))
    applied = MessageReviewItem(_parsed("Applied", source_id="applied"), created_record_ids=[7])
    errored = MessageReviewItem(_parsed("Broken", forms=[], source_id="error"), error="parse failed")

    model = MessageReviewModel([plain_candidate, applied, errored])

    assert model.exclude([0, 1, 2]) == 1

    assert model[0].status == STATUS_EXCLUDED
    assert model[1].status == STATUS_APPLIED
    assert model[2].status == STATUS_ERROR


def test_summary_counts_and_filters_preserve_existing_public_keys() -> None:
    model = MessageReviewModel(
        [
            MessageReviewItem(_parsed("Candidate", source_id="candidate")),
            MessageReviewItem(_parsed("Excluded", forms=[], excluded=True, reason="tracked team not involved", source_id="excluded")),
            MessageReviewItem(_parsed("Missing date", forms=[_form(None)], source_id="date")),
            MessageReviewItem(_parsed("Applied", source_id="applied"), created_record_ids=[7]),
            MessageReviewItem(_parsed("Broken", forms=[], source_id="error"), error="parse failed"),
        ]
    )

    counts = model.summary_counts()

    assert counts["total"] == 5
    assert counts["candidates"] == 1
    assert counts["applied"] == 1
    assert counts["excluded"] == 1
    assert counts["date_needed"] == 1
    assert counts["errors"] == 1
    assert counts["changed_review_needed"] == 0

    assert model.filtered_indexes("all") == [0, 1, 2, 3, 4]
    assert model.filtered_indexes(STATUS_APPROVED) == []
