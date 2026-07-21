"""UX tests for the bulk rating before-save preview dialog."""

from __future__ import annotations

import os

import pytest
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QLabel

from core.i18n import tr
from core.roster.bulk_rating import (
    BulkRatingPlan,
    PlayerRatingChange,
    RatingCellChange,
    RatingCellSkip,
)
from gui.widgets.bulk_rating_dialog import BulkRatingPreviewDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _plan() -> BulkRatingPlan:
    return BulkRatingPlan(
        scope_player_ids=(101, 102, 103),
        changes=(
            PlayerRatingChange(
                player_id=101,
                original_row=("100", "80"),
                updated_row=("110", "88"),
                fieldnames=("Contact vL", "Contact vL"),
                cells=(
                    RatingCellChange("Contact vL", 0, "100", "110"),
                    RatingCellChange("Contact vL", 1, "80", "88"),
                ),
            ),
        ),
        unchanged=((102, "selected rule produced no cell changes"),),
        skipped=((999, "player is not present in the roster"),),
        skipped_cells=(
            RatingCellSkip(103, "Power vR", 0, "invalid numeric value"),
        ),
    )


def test_preview_dialog_shows_summary_and_before_after_table(qapp) -> None:
    dialog = BulkRatingPreviewDialog(
        _plan(),
        {101: "Alpha Hitter", 102: "Beta Pitcher", 103: "Gamma Catcher"},
    )

    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "1" in labels
    assert "2" in labels
    assert "Alpha Hitter" == dialog.change_table.item(0, 0).text()
    assert "Contact vL" == dialog.change_table.item(0, 1).text()
    assert "100" == dialog.change_table.item(0, 2).text()
    assert "110" == dialog.change_table.item(0, 3).text()
    assert "Contact vL #2" == dialog.change_table.item(1, 1).text()


def test_preview_dialog_shows_skipped_and_empty_categories(qapp) -> None:
    dialog = BulkRatingPreviewDialog(
        _plan(),
        {101: "Alpha Hitter", 102: "Beta Pitcher", 103: "Gamma Catcher"},
    )

    details = dialog.detail_text.toPlainText()
    assert "Beta Pitcher" in details
    assert "selected rule produced no cell changes" in details
    assert "999" in details
    assert "player is not present in the roster" in details
    assert "Gamma Catcher" in details
    assert "Power vR" in details
    assert "invalid numeric value" in details

    empty_plan = BulkRatingPlan((1,), (), (), (), ())
    empty_dialog = BulkRatingPreviewDialog(empty_plan, {})
    assert tr("- None") in empty_dialog.detail_text.toPlainText()


def test_preview_dialog_uses_cancel_as_default_escape_path(qapp) -> None:
    dialog = BulkRatingPreviewDialog(_plan(), {101: "Alpha Hitter"})

    cancel = dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    assert cancel.isDefault()

    dialog.reject()
    assert dialog.result() == BulkRatingPreviewDialog.DialogCode.Rejected
