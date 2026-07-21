"""UX tests for the bulk rating before-save preview dialog."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QLabel, QPushButton

from core.i18n import tr
from core.roster.bulk_rating import (
    BulkRatingPlan,
    PlayerRatingChange,
    RatingCellChange,
    RatingCellSkip,
)
from gui.widgets.bulk_rating_dialog import BulkRatingPreviewDialog, BulkRatingSaveResultDialog

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


def test_save_result_dialog_shows_outputs_backups_and_actions(qapp, tmp_path: Path) -> None:
    output = tmp_path / "mod_mlb_rosters.txt"
    backup = tmp_path / "backup" / "mod_mlb_rosters.txt.bak"
    output.write_text("out", encoding="utf-8")
    backup.parent.mkdir()
    backup.write_text("backup", encoding="utf-8")
    opened: list[Path] = []
    dialog = BulkRatingSaveResultDialog(
        changed_players=2,
        changed_cells=5,
        output_paths=[output],
        backup_paths=[backup],
        opener=lambda path: opened.append(Path(path)) or True,
    )

    details = dialog.detail_text.toPlainText()
    assert str(output) in details
    assert str(backup) in details
    assert tr("Use these backups to restore the original roster files.") in details
    labels = [button.text() for button in dialog.findChildren(QPushButton)]
    assert tr("Open Output Folder") in labels
    assert tr("Open Backup Folder") in labels

    dialog.output_button.click()
    dialog.backup_button.click()

    assert output.parent in opened
    assert backup.parent in opened


def test_save_result_dialog_merges_same_folder_and_keeps_warning_on_open_failure(
    qapp,
    tmp_path: Path,
) -> None:
    output = tmp_path / "mod_mlb_rosters.txt"
    backup = tmp_path / "mod_mlb_rosters.txt.bak"
    output.write_text("out", encoding="utf-8")
    backup.write_text("backup", encoding="utf-8")
    dialog = BulkRatingSaveResultDialog(
        changed_players=1,
        changed_cells=1,
        output_paths=[output],
        backup_paths=[backup],
        opener=lambda _path: False,
    )

    labels = [button.text() for button in dialog.findChildren(QPushButton)]
    assert tr("Open Output and Backup Folder") in labels
    assert tr("Open Output Folder") not in labels
    assert tr("Open Backup Folder") not in labels

    dialog.output_button.click()

    assert not dialog.warning_label.isHidden()
    assert str(tmp_path) in dialog.warning_label.text()
    assert str(output) in dialog.detail_text.toPlainText()


def test_save_result_dialog_close_and_escape_are_safe(qapp, tmp_path: Path) -> None:
    dialog = BulkRatingSaveResultDialog(
        changed_players=1,
        changed_cells=1,
        output_paths=[],
        backup_paths=[],
    )

    close = dialog.buttons.button(QDialogButtonBox.StandardButton.Close)
    assert close is not None
    assert close.isDefault()

    dialog.reject()
    assert dialog.result() == BulkRatingSaveResultDialog.DialogCode.Rejected
