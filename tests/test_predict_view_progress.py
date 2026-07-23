"""Prediction table progress-bar delegate wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from gui.views.predict_view import PredictView, _GRADE_COL, _PROGRESS_COL
from gui.widgets.milestone_progress_delegate import (
    IS_NEAR_ROLE,
    PROGRESS_ROLE,
    MilestoneProgressDelegate,
)
from gui.widgets.table_widgets import NumericSortItem

ROOT = Path(__file__).resolve().parent.parent

_STATUS_COL = 5


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def predict_view(qapp, tmp_path):
    milestones = load_milestones(ROOT / "data" / "milestones.csv")
    milestone = milestones.get_by_key("bat_career_hr_500")
    assert milestone is not None

    aggregator = Aggregator(tmp_path / "predict.db")
    aggregator.upsert_player(90001, "Near Slugger", "Near Slugger")
    aggregator.upsert_player(90002, "Distant Slugger", "Distant Slugger")
    aggregator.upsert_milestone_predictions(
        [
            {
                "player_id": 90001,
                "milestone_key": milestone.key,
                "season": 2026,
                "player_name": "Near Slugger",
                "milestone_label": milestone.label,
                "grade": milestone.grade,
                "current_value": milestone.threshold - 5,
                "threshold": milestone.threshold,
                "remaining": 5,
                "progress_pct": 99.0,
                "season_note": "pre_season",
            },
            {
                "player_id": 90002,
                "milestone_key": milestone.key,
                "season": 2026,
                "player_name": "Distant Slugger",
                "milestone_label": milestone.label,
                "grade": milestone.grade,
                "current_value": milestone.threshold - 200,
                "threshold": milestone.threshold,
                "remaining": 200,
                "progress_pct": 60.0,
                "season_note": "pre_season",
            },
        ]
    )
    settings = AppSettings(current_season=2026, season_games_total=162)
    view = PredictView(aggregator, milestones, settings)
    view.refresh()
    yield view
    aggregator.close()


def test_progress_column_uses_delegate_with_numeric_sort_data(
    predict_view: PredictView,
) -> None:
    table = predict_view.table
    assert table.columnCount() == 7
    assert isinstance(
        table.itemDelegateForColumn(_PROGRESS_COL), MilestoneProgressDelegate
    )
    assert table.rowCount() == 2

    for row in range(table.rowCount()):
        cell = table.item(row, _PROGRESS_COL)
        assert isinstance(cell, NumericSortItem)
        progress = cell.data(PROGRESS_ROLE)
        assert progress is not None
        assert 0.0 <= float(progress) <= 100.0
        assert isinstance(cell.data(IS_NEAR_ROLE), bool)


def test_progress_column_sorts_by_numeric_percentage(
    predict_view: PredictView,
) -> None:
    table = predict_view.table
    table.sortItems(_PROGRESS_COL, Qt.SortOrder.AscendingOrder)
    assert [
        float(table.item(row, _PROGRESS_COL).data(PROGRESS_ROLE))
        for row in range(table.rowCount())
    ] == [60.0, 99.0]

    table.sortItems(_PROGRESS_COL, Qt.SortOrder.DescendingOrder)
    assert [
        float(table.item(row, _PROGRESS_COL).data(PROGRESS_ROLE))
        for row in range(table.rowCount())
    ] == [99.0, 60.0]


def test_only_near_row_is_flagged_red_and_matches_status_column(
    predict_view: PredictView,
) -> None:
    table = predict_view.table
    seen_near = False
    for row in range(table.rowCount()):
        status_cell = table.item(row, _STATUS_COL)
        progress_cell = table.item(row, _PROGRESS_COL)
        is_near_status = bool(status_cell.text())
        is_near_flag = bool(progress_cell.data(IS_NEAR_ROLE))
        assert is_near_status == is_near_flag
        seen_near = seen_near or is_near_flag
    assert seen_near, "expected the near-threshold row to be flagged as near"


def test_near_rows_only_mark_the_progress_bar_red(
    predict_view: PredictView,
) -> None:
    """Near styling is carried only by the progress delegate's role."""
    table = predict_view.table
    seen_near = False
    for row in range(table.rowCount()):
        progress_cell = table.item(row, _PROGRESS_COL)
        if not bool(progress_cell.data(IS_NEAR_ROLE)):
            continue
        seen_near = True
        for col in range(table.columnCount()):
            if col == _PROGRESS_COL:
                continue
            cell = table.item(row, col)
            if col == _GRADE_COL:
                # Grade cells keep their normal grade styling.
                continue
            assert cell.background().style() == Qt.BrushStyle.NoBrush
            assert cell.foreground().style() == Qt.BrushStyle.NoBrush
    assert seen_near, "expected the near-threshold row to be flagged as near"


def test_double_click_still_emits_player_detail_request(
    predict_view: PredictView,
) -> None:
    table = predict_view.table
    assert table.rowCount() == 2
    emitted: list[int] = []
    predict_view.player_detail_requested.connect(emitted.append)

    cell = table.item(0, 0)
    expected_id = int(cell.data(Qt.ItemDataRole.UserRole))
    predict_view._open_player_details(0, 0)

    assert emitted == [expected_id]
