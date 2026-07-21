"""UX-focused tests for milestone history filtering and selection."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
import gui.views.milestone_view as milestone_module
from gui.views.milestone_view import MilestoneView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


RECORDS = [
    {
        "id": 1,
        "achieved_date": "2026-07-01",
        "player_id": 0,
        "player_name": "",
        "team": "SEA",
        "milestone_key": "team_game_hits_20",
        "milestone_label": "Team Hits",
        "scope": "team_game",
        "games_at_achievement": None,
        "opponent_team": "OAK",
        "opponent_player": "",
        "description": "Team hit milestone",
        "notes": "",
        "is_manual": 0,
    },
    {
        "id": 2,
        "achieved_date": "2026-07-02",
        "player_id": 0,
        "player_name": "",
        "team": "SEA",
        "milestone_key": "team_season_wins_100",
        "milestone_label": "Team Wins",
        "scope": "team_season",
        "games_at_achievement": None,
        "opponent_team": "",
        "opponent_player": "",
        "description": "Team season milestone",
        "notes": "",
        "is_manual": 0,
    },
]


class FakeChecker:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def get_recorded_milestones(
        self,
        *,
        scope=None,
        season=None,
        search="",
        subject="all",
        team=None,
    ):
        rows = list(RECORDS)
        if scope:
            rows = [row for row in rows if row["scope"] == scope]
        if team:
            rows = [row for row in rows if row["team"] == team]
        if search:
            needle = search.lower()
            rows = [
                row
                for row in rows
                if needle in row["milestone_label"].lower()
                or needle in row["team"].lower()
                or needle in row["description"].lower()
            ]
        if subject == "personal":
            rows = [row for row in rows if int(row.get("player_id") or 0) > 0]
        elif subject == "team":
            rows = [row for row in rows if int(row.get("player_id") or 0) == 0]
        _ = season
        return rows


class FakeMilestones:
    def get_by_key(self, key: str):
        return SimpleNamespace(label=key.replace("_", " ").title(), grade="common")


class FakeAggregator:
    def get_milestone_record_by_id(self, record_id: int):
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
    if item is None:
        return None
    return item.data(Qt.ItemDataRole.UserRole)


def test_filter_summary_shows_count_and_inactive_reset(milestone_view) -> None:
    assert milestone_view.table_panel.table.rowCount() == 2
    assert tr("Showing {shown:,} / {total:,} records").format(
        shown=2, total=2
    ) in milestone_view.filter_summary_label.text()
    assert tr(" · No active filters").strip() in milestone_view.filter_summary_label.text()
    assert not milestone_view.reset_filters_button.isEnabled()


def test_empty_filter_result_can_reset_in_one_action(milestone_view) -> None:
    milestone_view.table_panel.filter_bar.search_input.setText("no matching record")

    assert milestone_view.table_panel.table.rowCount() == 0
    assert not milestone_view.empty_state.isHidden()
    assert tr("Showing {shown:,} / {total:,} records").format(
        shown=0, total=2
    ) in milestone_view.filter_summary_label.text()
    assert tr("Search: {text}").format(text="").split(":", 1)[0] in (
        milestone_view.filter_summary_label.text()
    )
    assert milestone_view.reset_filters_button.isEnabled()
    assert milestone_view.reset_filters_button.toolTip()

    milestone_view.reset_filters()

    assert milestone_view.table_panel.filter_bar.search_input.text() == ""
    assert milestone_view.table_panel.table.rowCount() == 2
    assert not milestone_view.reset_filters_button.isEnabled()


def test_refresh_preserves_selected_record_when_it_still_matches(milestone_view) -> None:
    assert milestone_view.table_panel.table.rowCount() == 2
    assert milestone_view.table_panel.table.selectRow(1) is None
    assert _selected_record_id(milestone_view) == 2

    milestone_view.refresh()

    assert _selected_record_id(milestone_view) == 2
