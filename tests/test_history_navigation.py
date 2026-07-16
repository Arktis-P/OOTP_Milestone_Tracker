"""Focused tests for history classification and player-detail routing."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from gui.app import MainWindow
from core.i18n import tr
from core.milestone.definitions import load_milestones
from gui.views.milestone_view import (
    milestone_event_type,
    milestone_is_manual,
    milestone_record_matches,
    select_record_row,
    source_display_label,
)
from gui.views.stats_view import StatsView


def _definition(**overrides):
    values = {
        "category": "batting",
        "stat": "career_hr",
        "description_template": "career_batting_stat",
        "grade": "rare",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_milestone_event_type_uses_scope_key_and_definition_metadata() -> None:
    assert milestone_event_type(
        {"milestone_key": "bat_career_hr_500", "scope": "career", "player_id": 7},
        _definition(),
    ) == "official"
    assert milestone_event_type(
        {"milestone_key": "team_game_hits_20", "scope": "team_game", "player_id": 0, "team": "SEA"},
        _definition(category="team", stat="award_championship"),
    ) == "team"
    assert milestone_event_type(
        {"milestone_key": "streak_hitting", "scope": "streak", "player_id": 7},
        None,
    ) == "streak"
    assert milestone_event_type(
        {"milestone_key": "bat_season_award_mvp", "scope": "season", "player_id": 7},
        _definition(stat="award_mvp"),
    ) == "award"
    assert milestone_event_type(
        {"milestone_key": "manual_transfer_trade", "scope": "manual_event", "player_id": 7},
        None,
    ) == "transfer"
    assert milestone_event_type(
        {"milestone_key": "manual_injury", "scope": "manual_event", "player_id": 7},
        None,
    ) == "injury"
    assert milestone_event_type(
        {"milestone_key": "personal_best_game_hr", "scope": "manual_event", "player_id": 7},
        None,
    ) == "personal"
    assert milestone_event_type(
        {"milestone_key": "near_milestone_hr", "scope": "manual_event", "player_id": 7},
        None,
    ) == "quasi"
    # Official scopes remain stable when a bundle definition was removed.
    assert milestone_event_type(
        {"milestone_key": "legacy_career_mark", "scope": "career", "player_id": 7},
        None,
    ) == "official"


def test_timeline_filters_compose_event_grade_and_source() -> None:
    record = {
        "milestone_key": "bat_career_hr_500",
        "scope": "career",
        "player_id": 7,
        "is_manual": 0,
    }
    definition = _definition()

    assert milestone_record_matches(
        record, definition, event_type="official", grade="rare", source="automatic"
    )
    assert not milestone_record_matches(record, definition, event_type="award")
    assert not milestone_record_matches(record, definition, grade="epic")
    assert not milestone_record_matches(record, definition, source="manual")


def test_milestone_is_manual_treats_team_manual_scope_as_manual() -> None:
    # Historical/current team_manual records must be Manual even if is_manual is 0.
    record = {"scope": "team_manual", "is_manual": 0}
    assert milestone_is_manual(record) is True
    assert source_display_label(milestone_is_manual(record)) == tr("Manual")


def test_milestone_is_manual_keeps_team_game_and_team_season_automatic() -> None:
    for scope in ("team_game", "team_season"):
        record = {"scope": scope, "is_manual": 0}
        assert milestone_is_manual(record) is False
        assert source_display_label(milestone_is_manual(record)) == tr("Automatic")


def test_milestone_is_manual_falls_back_to_is_manual_flag() -> None:
    assert milestone_is_manual({"scope": "career", "is_manual": 1}) is True
    assert milestone_is_manual({"scope": "career", "is_manual": 0}) is False


def test_timeline_filters_treat_team_manual_scope_as_manual_source() -> None:
    record = {
        "milestone_key": "team_manual_note",
        "scope": "team_manual",
        "player_id": 0,
        "team": "SEA",
        "is_manual": 0,
    }
    assert milestone_record_matches(record, None, source="manual")
    assert not milestone_record_matches(record, None, source="automatic")


def test_title_definitions_are_classified_as_awards() -> None:
    milestones = load_milestones(
        Path(__file__).resolve().parent.parent / "data" / "milestones.csv"
    )
    for key in (
        "bat_season_title_batting_champion",
        "pit_season_title_era_leader",
    ):
        definition = milestones.get_by_key(key)
        assert definition is not None
        assert milestone_event_type(
            {"milestone_key": key, "scope": "season", "player_id": 7},
            definition,
        ) == "award"


def test_main_window_player_route_selects_stats_before_focus() -> None:
    window = MagicMock()
    window._stats_view = MagicMock()

    MainWindow._navigate_to_player_details(window, 42)

    window._set_current_page.assert_called_once_with(window._stats_view)
    window._stats_view.focus_player.assert_called_once_with(42)


def test_prediction_route_distinguishes_near_item_from_view_all() -> None:
    window = MagicMock()
    window._predict_view = MagicMock()

    MainWindow._navigate_to_predict(window, -1, "")
    window._predict_view.focus_player.assert_called_once_with(None, near_only=False)

    window._predict_view.focus_player.reset_mock()
    MainWindow._navigate_to_predict(window, 42, "bat_career_hr_500")
    window._predict_view.focus_player.assert_called_once_with(42, near_only=True)


def test_milestone_route_can_focus_streak_scope() -> None:
    window = MagicMock()
    window._milestone_view = MagicMock()

    MainWindow._navigate_to_milestone(window, {"scope": "streak"})

    window._milestone_view.focus_scope.assert_called_once_with("streak")
    window._set_current_page.assert_called_once_with(window._milestone_view)


def test_stats_focus_player_clears_filters_and_selects_matching_item() -> None:
    view = MagicMock()
    view._players_by_id = {42: {"player_id": 42}}
    item = MagicMock()
    item.data.return_value = 42
    view.player_list.count.return_value = 1
    view.player_list.item.return_value = item

    assert StatsView.focus_player(view, 42)

    view.reload_players.assert_called_once()
    view.player_search.clear.assert_called_once()
    view.position_combo.setCurrentIndex.assert_called_once_with(0)
    view._apply_player_filter.assert_called_once()
    view.player_list.setCurrentRow.assert_called_once_with(0)


def test_highlight_finds_record_id_after_table_sort(qapp) -> None:
    table = QTableWidget(0, 1)
    table.setSortingEnabled(False)
    for text, record_id in (("2026-01-01", 10), ("2026-12-31", 20)):
        row = table.rowCount()
        table.insertRow(row)
        item = QTableWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, record_id)
        table.setItem(row, 0, item)
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.DescendingOrder)

    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == 20
    assert select_record_row(table, 10)
    assert table.item(table.currentRow(), 0).data(Qt.ItemDataRole.UserRole) == 10


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])
