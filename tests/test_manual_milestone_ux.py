from __future__ import annotations

import os
from datetime import date

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from core.milestone.manual_entry import ManualInjuryFormData
from core.stats.aggregator import Aggregator
from gui.widgets.guided_milestone_form import GuidedRecordEditor
from gui.widgets.manual_milestone_dialog import ManualMilestoneDialog, _TAB_INJURY

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeMilestones:
    all_milestones = []

    def get_by_key(self, _key):
        return None


class FakeSettings:
    tracked_teams = ["SEA"]
    custom_mlb_teams = {}
    import_export_dir = ""
    initial_stats_dir = ""
    season_games_total = 162

    def get_ratio_qualifiers(self):
        return {}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def aggregator(tmp_path):
    agg = Aggregator(tmp_path / "manual_ux.db")
    yield agg
    agg.close()


@pytest.fixture
def dialog(qapp, aggregator):
    widget = ManualMilestoneDialog(aggregator, FakeMilestones(), FakeSettings())
    yield widget
    widget.deleteLater()


def test_manual_entry_defaults_to_one_at_a_time_mode(dialog) -> None:
    assert dialog.mode_stack.currentWidget() is dialog.single_mode_page
    assert dialog.bulk_save_button is not None
    assert not dialog.bulk_save_button.isVisible()
    assert tr(
        "Default mode: add one record with a guided form. Use bulk mode only for multiple records."
    ) == dialog.bulk_status_label.text()


def test_bulk_mode_is_explicit_and_shows_save_count(dialog) -> None:
    dialog._show_bulk_mode()

    assert dialog.mode_stack.currentWidget() is dialog.stack
    assert dialog.bulk_save_button is not None
    assert not dialog.bulk_save_button.isHidden()
    assert "0" in dialog.bulk_status_label.text()


def test_extracted_injury_reuses_manual_form_population(dialog) -> None:
    form = ManualInjuryFormData(
        player_name="Aaron Judge",
        achieved_date=date(2026, 5, 10),
        injury_label="Hamstring",
        duration="3 days",
        team="Seattle Mariners",
        season=2026,
        description="Hamstring for 3 days",
        notes="source:message1433",
    )

    dialog.add_extracted_injury(form)

    assert dialog.tabs.currentIndex() == _TAB_INJURY
    assert dialog.mode_stack.currentWidget() is dialog.stack
    assert "1" in dialog.bulk_status_label.text()
    assert dialog.injury_table.rowCount() >= 1
    assert dialog.injury_table.cellWidget(0, 0).text() == "2026-05-10"
    assert dialog.injury_table.cellWidget(0, 2).text() == "Hamstring"


def test_manual_dialog_exposes_shared_guided_form(dialog) -> None:
    form = ManualInjuryFormData(
        player_name="Aaron Judge",
        achieved_date=date(2026, 5, 10),
        injury_label="Hamstring",
        duration="3 days",
        team="Seattle Mariners",
        season=2026,
        description="Hamstring for 3 days",
        notes="source:message1433",
    )

    guided = dialog.create_guided_form_for_extracted([form])
    try:
        assert guided.edited_values()["injury_label"] == "Hamstring"
        labels = [guided.table.item(row, 0).text() for row in range(guided.table.rowCount())]
        assert ("Injury" in labels) or ("부상" in labels)
        assert "injury_label" not in labels
    finally:
        guided.deleteLater()


def test_guided_form_for_extracted_renders_real_typed_editor_with_context(dialog) -> None:
    """The reusable message-extraction entry point must render the same
    typed GuidedRecordEditor as manual single-record entry (with real
    aggregator/settings/milestones context), not just a translated table."""
    form = ManualInjuryFormData(
        player_name="Aaron Judge",
        achieved_date=date(2026, 5, 10),
        injury_label="Hamstring",
        duration="3 days",
        team="Seattle Mariners",
        season=2026,
        description="Hamstring for 3 days",
        notes="source:message1433",
    )

    guided = dialog.create_guided_form_for_extracted([form])
    try:
        assert isinstance(guided.editor, GuidedRecordEditor)
        page = guided.editor._active_page
        assert page.injury_label_edit.text() == "Hamstring"
        # Source provenance (notes) is shown separately and protected from edits.
        assert page.notes_edit.isReadOnly()
        assert "source:message1433" in guided.source_id_label.text()
    finally:
        guided.deleteLater()
