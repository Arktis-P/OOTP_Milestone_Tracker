from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import gui.views.milestone_view as milestone_module
from gui.views.milestone_view import MilestoneView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RECORDS = [
    {"id": 1, "achieved_date": "2026-07-01", "player_id": 0, "player_name": "",
     "team": "SEA", "milestone_key": "team_game_hits_20", "milestone_label": "Team Hits",
     "scope": "team_game", "games_at_achievement": None, "opponent_team": "OAK",
     "opponent_player": "", "description": "Team hit milestone", "notes": "", "is_manual": 0},
    {"id": 2, "achieved_date": "2026-07-02", "player_id": 0, "player_name": "",
     "team": "SEA", "milestone_key": "team_season_wins_100", "milestone_label": "Team Wins",
     "scope": "team_season", "games_at_achievement": None, "opponent_team": "",
     "opponent_player": "", "description": "Team season milestone", "notes": "", "is_manual": 0},
]


class FakeChecker:
    def __init__(self, *_args, **_kwargs):
        pass

    def get_recorded_milestones(self, *, scope=None, season=None, search="",
                                subject="all", team=None):
        rows = list(RECORDS)
        if scope:
            rows = [row for row in rows if row["scope"] == scope]
        if team:
            rows = [row for row in rows if row["team"] == team]
        if search:
            needle = search.lower()
            rows = [row for row in rows if needle in row["milestone_label"].lower()]
        return rows


class FakeMilestones:
    def get_by_key(self, key):
        return SimpleNamespace(label=key, grade="common")


class FakeAggregator:
    def get_milestone_record_by_id(self, record_id):
        return next((row for row in RECORDS if row["id"] == record_id), None)


class FakeSettings:
    season_games_total = 162
    tracked_teams = ["SEA"]
    custom_mlb_teams = []
    import_mlb_only = True
    import_export_dir = ""
    initial_stats_dir = ""
    game_logs_dir = ""

    def get_ratio_qualifiers(self):
        return {}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def milestone_view(monkeypatch, qapp):
    monkeypatch.setattr(milestone_module, "MilestoneChecker", FakeChecker)
    monkeypatch.setattr(milestone_module, "load_korean_name_mapper", lambda: None)
    monkeypatch.setattr(milestone_module, "load_player_full_names", lambda _agg: {})
    monkeypatch.setattr(milestone_module, "load_roster_player_names", lambda _path: {})
    view = MilestoneView(FakeAggregator(), FakeMilestones(), FakeSettings())
    yield view
    view.deleteLater()


def _selected_record_id(view: MilestoneView) -> int | None:
    item = view.table_panel.table.item(view.table_panel.table.currentRow(), 0)
    return None if item is None else item.data(Qt.ItemDataRole.UserRole)


def test_filter_summary_reset_and_empty_state(milestone_view) -> None:
    assert "Showing 2 of 2 records" in milestone_view.filter_summary_label.text()
    assert not milestone_view.reset_filters_button.isEnabled()

    milestone_view.table_panel.filter_bar.search_input.setText("missing")
    assert milestone_view.table_panel.table.rowCount() == 0
    assert "Showing 0 of 2 records" in milestone_view.filter_summary_label.text()
    assert milestone_view.reset_filters_button.isEnabled()

    milestone_view.reset_filters()
    assert milestone_view.table_panel.table.rowCount() == 2
    assert not milestone_view.reset_filters_button.isEnabled()


def test_refresh_preserves_selected_record(milestone_view) -> None:
    milestone_view.table_panel.table.selectRow(1)
    assert _selected_record_id(milestone_view) == 2
    milestone_view.refresh()
    assert _selected_record_id(milestone_view) == 2
