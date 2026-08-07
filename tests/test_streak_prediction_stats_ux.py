from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import tr
from core.streak.center_model import EndedStreak, StreakCenterModel
from core.streak.read_model import ActiveStreak
from gui.views.predict_view import _grade_label
from gui.views.predict_view import PREDICTION_DETAIL_ROLE
from gui.widgets.milestone_progress_delegate import PROGRESS_ROLE
from gui.views.stats_view import StatsView
from gui.views.streak_view import StreakView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_predict_grade_labels_are_display_names(qapp) -> None:
    assert _grade_label("uncommon") == tr("Uncommon")
    assert _grade_label("legendary") == tr("Legendary")


def test_prediction_detail_role_does_not_conflict_with_progress_role() -> None:
    assert PREDICTION_DETAIL_ROLE != PROGRESS_ROLE


def test_stats_ratio_values_are_formatted_for_readability() -> None:
    assert StatsView._format_stat_value("AVG", 0.312345) == "0.312"
    assert StatsView._format_stat_value("ERA", 2.987) == "2.99"
    assert StatsView._format_stat_value("HR", 17) == 17


def test_streak_view_loads_as_independent_main_page(monkeypatch, qapp) -> None:
    active = ActiveStreak(
        season=2026,
        player_id=1,
        player_name="Alpha",
        team="SEA",
        streak_type="hit",
        label="Hitting streak",
        unit="games",
        value=12,
        display_value="12",
        start_date="2026-07-01",
        last_date="2026-07-12",
    )
    ended = EndedStreak(
        record_id=10,
        season=2026,
        player_id=1,
        player_name="Alpha",
        team="SEA",
        streak_type="hit",
        label="Hitting streak",
        event_type="streak_ended",
        event_reason="Ended",
        value=14,
        display_value="14",
        unit="games",
        achieved_date="2026-07-20",
        description="Ended at 14 games",
    )

    def fake_load(_aggregator, _season, *, filters):
        return StreakCenterModel(
            active=[active],
            ended=[ended],
            player_options=["Alpha"],
            team_options=["SEA"],
            type_options=[("hit", "Hitting streak")],
            note="",
        )

    monkeypatch.setattr("gui.views.streak_view.load_streak_center", fake_load)
    view = StreakView(SimpleNamespace(), 2026)
    try:
        assert view.active_table.rowCount() == 1
        assert view.ended_table.rowCount() == 1
        assert view.player_filter.count() == 2
        assert "Alpha" == view.active_table.item(0, 0).text()
    finally:
        view.deleteLater()
