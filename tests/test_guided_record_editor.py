from __future__ import annotations

import os
from datetime import date

import pytest
from PyQt6.QtWidgets import QApplication, QDateEdit, QLabel

from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
)
from core.roster.player_registry import PlayerRegistry
from core.stats.aggregator import Aggregator
from gui.widgets.guided_milestone_form import GuidedMilestoneForm, GuidedRecordEditor
from gui.widgets.single_record_dialogs import (
    SingleInjuryEntryDialog,
    SingleMilestoneEntryDialog,
    SingleTransferEntryDialog,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
    agg = Aggregator(tmp_path / "guided_editor.db")
    yield agg
    agg.close()


@pytest.fixture
def settings():
    return FakeSettings()


@pytest.fixture
def milestones():
    career_hr = MilestoneDefinition(
        key="career_hr_500",
        label="500 Career Home Runs",
        stat="career_hr",
        threshold=500,
        scope="career",
        category="batting",
    )
    team_wins = MilestoneDefinition(
        key="team_season_wins_100",
        label="100 Team Wins",
        stat="team_wins",
        threshold=100,
        scope="team_season",
        category="team",
    )
    return MilestoneDefinitions(batting=[career_hr], pitching=[], team=[team_wins])


@pytest.fixture
def player_id(aggregator):
    return PlayerRegistry(aggregator).add_manual_player("Aaron Judge")


def test_guided_form_uses_typed_editor_without_message_review_context(qapp) -> None:
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

    widget = GuidedMilestoneForm([form])
    try:
        dates = widget.findChildren(QDateEdit)
        assert dates
        assert dates[0].calendarPopup()
        assert widget.edited_values()["injury_label"] == "Hamstring"
        assert "source_id" not in widget.edited_values()
        assert widget.editor._injury_page.notes_edit.isReadOnly()
        assert "source:message1433" in widget.source_id_label.text()
        assert widget.build_form_data() == form
    finally:
        widget.deleteLater()


def test_guided_editor_builds_transfer_data_and_reuses_validation(qapp) -> None:
    editor = GuidedRecordEditor()
    form = ManualTransferFormData(
        achieved_date=date(2026, 7, 1),
        joining_players="Aaron Judge",
        leaving_players="",
        event_type="trade",
        join_team="Seattle Mariners",
        counterpart_team="New York Yankees",
        season=2026,
        description="Aaron Judge trade",
        notes="source:message99",
    )
    try:
        editor.set_form(form)
        assert editor.edited_values()["event_type"] == "trade"
        assert editor.validate() == []
        assert editor.build_form_data() == form

        editor._transfer_page.join_team_combo.setCurrentText("")
        assert editor.validate()
    finally:
        editor.deleteLater()


def test_guided_editor_blocks_invalid_milestone_numeric_input(qapp) -> None:
    editor = GuidedRecordEditor()
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 7, 24),
        player_id=101,
        team=None,
        milestone_key="award_mvp",
        season=2026,
        achieved_value=1,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="MVP award",
        notes="source:message1",
    )
    try:
        editor.set_form(form)
        editor._milestone_page.value_combo.setCurrentText("not-a-number")

        assert editor.validate()
        assert editor.edited_values()["achieved_value"] == "not-a-number"
    finally:
        editor.deleteLater()


def test_milestone_team_round_trip_with_full_context(qapp, aggregator, settings, milestones) -> None:
    editor = GuidedRecordEditor(aggregator, settings, milestones)
    try:
        form = ManualMilestoneFormData(
            target="team",
            achieved_date=date(2026, 6, 1),
            player_id=None,
            team="Seattle Mariners",
            milestone_key="team_season_wins_100",
            season=2026,
            achieved_value=100,
            games_at_achievement=150,
            opponent_team="",
            opponent_player="",
            description="Clinched 100 wins",
            notes="",
        )
        editor.set_form(form)
        assert editor.validate() == []
        rebuilt = editor.build_form_data()
        assert rebuilt.team == "Seattle Mariners"
        assert rebuilt.milestone_key == "team_season_wins_100"
        assert editor.selected_milestone().key == "team_season_wins_100"
    finally:
        editor.deleteLater()


def test_milestone_player_round_trip_resolves_manual_player(qapp, aggregator, settings, milestones, player_id) -> None:
    editor = GuidedRecordEditor(aggregator, settings, milestones)
    try:
        form = ManualMilestoneFormData(
            target="player",
            achieved_date=date(2026, 5, 10),
            player_id=player_id,
            team=None,
            milestone_key="career_hr_500",
            season=2026,
            achieved_value=500,
            games_at_achievement=550,
            opponent_team="",
            opponent_player="",
            description="500th home run",
            notes="",
        )
        editor.set_form(form)
        rebuilt = editor.build_form_data()
        assert rebuilt.player_id == player_id
    finally:
        editor.deleteLater()


def test_player_combo_has_autocomplete_with_full_context(qapp, aggregator, settings, milestones) -> None:
    editor = GuidedRecordEditor(aggregator, settings, milestones)
    try:
        editor.set_record_type("milestone")
        page = editor._active_page
        assert page.player_combo.completer() is not None
        assert page.player_combo.isEditable()
    finally:
        editor.deleteLater()


def test_single_dialogs_share_editor_and_validation_with_message_review_form(
    qapp, aggregator, settings, milestones
) -> None:
    """Manual single-record entry and message-review corrections must reject
    the same invalid injury input identically, since both are thin layers
    over the same GuidedRecordEditor + validate_manual_injury."""
    manual_dialog = SingleInjuryEntryDialog(aggregator, settings)
    guided = GuidedMilestoneForm(
        [
            ManualInjuryFormData(
                player_name="",
                achieved_date=date(2026, 1, 1),
                injury_label="",
                duration="",
                team="",
                season=2026,
                description="",
                notes="",
            )
        ],
        aggregator=aggregator,
        settings=settings,
    )
    try:
        assert isinstance(manual_dialog.editor, GuidedRecordEditor)
        manual_dialog.editor._injury_page.player_combo.setCurrentText("")
        manual_dialog.editor._injury_page.injury_label_edit.setText("")

        guided.editor._injury_page.player_combo.setCurrentText("")
        guided.editor._injury_page.injury_label_edit.setText("")

        assert sorted(manual_dialog.editor.validate()) == sorted(guided.validate())
        assert manual_dialog.editor.validate() != []
    finally:
        manual_dialog.deleteLater()
        guided.deleteLater()


def test_single_transfer_and_injury_dialogs_use_shared_editor(qapp, aggregator, settings) -> None:
    transfer_dialog = SingleTransferEntryDialog(aggregator, settings)
    injury_dialog = SingleInjuryEntryDialog(aggregator, settings)
    try:
        assert isinstance(transfer_dialog.editor, GuidedRecordEditor)
        assert isinstance(injury_dialog.editor, GuidedRecordEditor)
        assert isinstance(transfer_dialog.editor._active_page.date_edit, QDateEdit)
        assert transfer_dialog.editor._active_page.date_edit.calendarPopup()
    finally:
        transfer_dialog.deleteLater()
        injury_dialog.deleteLater()


def test_single_milestone_dialog_reports_errors_via_shared_validation(
    qapp, aggregator, settings, milestones
) -> None:
    from core.i18n import tr

    dialog = SingleMilestoneEntryDialog("milestone", aggregator, milestones, settings)
    try:
        dialog.editor._milestone_page.value_combo.setCurrentText("")
        errors = dialog.editor.validate()
        assert tr("Achieved value must be a number.") in errors
    finally:
        dialog.deleteLater()
