"""UX-focused tests for player search in StatsView."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gui.views.stats_view import StatsView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


PLAYERS = [
    {
        "player_id": 10,
        "full_name": "Alpha Hitter",
        "short_name": "A. Hitter",
        "primary_position": "RF",
        "is_pitcher": 0,
        "is_batter": 1,
    },
    {
        "player_id": 20,
        "full_name": "Beta Pitcher",
        "short_name": "B. Pitcher",
        "primary_position": "SP",
        "is_pitcher": 1,
        "is_batter": 0,
    },
    {
        "player_id": 30,
        "full_name": "Gamma Catcher",
        "short_name": "G. Catcher",
        "primary_position": "C",
        "is_pitcher": 0,
        "is_batter": 1,
    },
]


class FakeAggregator:
    db_path = ""

    def get_available_seasons(self):
        return [2026]

    def get_tracked_players(self, _teams, custom_teams=None):
        _ = custom_teams
        return list(PLAYERS)


class FakeSettings:
    current_season = 2026
    season_games_total = 162
    tracked_teams = ["SEA"]
    custom_mlb_teams = []
    import_mlb_only = True
    import_export_dir = ""
    initial_stats_dir = ""
    boxscore_dir = ""


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def stats_view(monkeypatch, qapp):
    def fake_refresh(self):
        player_id = self._selected_player_id()
        self.player_header.setText(f"Selected {player_id}" if player_id else "Please select")

    monkeypatch.setattr(StatsView, "_refresh_player_stats", fake_refresh)
    view = StatsView(FakeAggregator(), FakeSettings(), SimpleNamespace())
    yield view
    view.deleteLater()


def _selected_player_id(view: StatsView) -> int | None:
    item = view.player_list.currentItem()
    if item is None:
        return None
    return int(item.data(Qt.ItemDataRole.UserRole))


def test_search_filters_immediately_without_debounce(stats_view) -> None:
    assert stats_view.player_list.count() == 3

    stats_view.player_search.setText("beta")

    assert stats_view.player_list.count() == 1
    assert _selected_player_id(stats_view) == 20
    count_text = stats_view.player_count_label.text()
    assert "1" in count_text
    assert "3" in count_text


def test_empty_filter_result_shows_inline_reset(stats_view) -> None:
    stats_view.player_search.setText("missing player")

    assert stats_view.player_list.count() == 0
    assert not stats_view.empty_filter_panel.isHidden()
    count_text = stats_view.player_count_label.text()
    assert "0" in count_text
    assert "3" in count_text
    assert stats_view.player_search.toolTip()
    assert stats_view.reset_player_filters_button.accessibleName()

    stats_view.reset_player_filters()

    assert stats_view.player_search.text() == ""
    assert stats_view.position_combo.currentIndex() == 0
    assert stats_view.player_list.count() == 3
    assert stats_view.empty_filter_panel.isHidden()


def test_filter_preserves_existing_selection_when_present(stats_view) -> None:
    for row in range(stats_view.player_list.count()):
        item = stats_view.player_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == 20:
            stats_view.player_list.setCurrentRow(row)
            break
    assert _selected_player_id(stats_view) == 20

    stats_view.player_search.setText("pitcher")

    assert stats_view.player_list.count() == 1
    assert _selected_player_id(stats_view) == 20


def test_filter_falls_back_to_first_when_selection_disappears(stats_view) -> None:
    for row in range(stats_view.player_list.count()):
        item = stats_view.player_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == 20:
            stats_view.player_list.setCurrentRow(row)
            break
    assert _selected_player_id(stats_view) == 20

    stats_view.player_search.setText("alpha")

    assert stats_view.player_list.count() == 1
    assert _selected_player_id(stats_view) == 10
