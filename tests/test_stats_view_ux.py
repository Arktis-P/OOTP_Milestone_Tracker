from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gui.views.stats_view import StatsView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLAYERS = [
    {"player_id": 10, "full_name": "Alpha Hitter", "short_name": "A. Hitter",
     "primary_position": "RF", "is_pitcher": 0, "is_batter": 1},
    {"player_id": 20, "full_name": "Beta Pitcher", "short_name": "B. Pitcher",
     "primary_position": "SP", "is_pitcher": 1, "is_batter": 0},
    {"player_id": 30, "full_name": "Gamma Catcher", "short_name": "G. Catcher",
     "primary_position": "C", "is_pitcher": 0, "is_batter": 1},
]


class FakeAggregator:
    db_path = ""

    def get_available_seasons(self):
        return [2026]

    def get_tracked_players(self, _teams, custom_teams=None):
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
    monkeypatch.setattr(StatsView, "_refresh_player_stats", lambda self: None)
    view = StatsView(FakeAggregator(), FakeSettings(), SimpleNamespace())
    yield view
    view.deleteLater()


def _selected_player_id(view: StatsView) -> int | None:
    item = view.player_list.currentItem()
    return None if item is None else int(item.data(Qt.ItemDataRole.UserRole))


def test_search_filters_immediately_and_shows_count(stats_view) -> None:
    stats_view.player_search.setText("beta")

    assert stats_view.player_list.count() == 1
    assert _selected_player_id(stats_view) == 20
    assert "1/3" in stats_view.player_filter_summary.text()


def test_filter_preserves_selection_and_empty_state_is_actionable(stats_view) -> None:
    for row in range(stats_view.player_list.count()):
        if stats_view.player_list.item(row).data(Qt.ItemDataRole.UserRole) == 20:
            stats_view.player_list.setCurrentRow(row)
            break

    stats_view.player_search.setText("pitcher")
    assert _selected_player_id(stats_view) == 20

    stats_view.player_search.setText("missing")
    assert stats_view.player_list.count() == 0
    assert "0/3" in stats_view.player_filter_summary.text()
    assert "Clear the filter" in stats_view.info_label.text()
