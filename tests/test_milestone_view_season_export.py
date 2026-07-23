"""Season-final export validation UI behavior."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.i18n import get_language, set_language
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from gui.views import milestone_view as milestone_view_module
from gui.views.milestone_view import (
    MilestoneView,
    build_snapshot_incomplete_message,
    format_snapshot_validation_issue,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def english_i18n():
    previous = get_language()
    set_language("en")
    yield
    set_language(previous)


@pytest.fixture
def view(qapp, tmp_path: Path):
    aggregator = Aggregator(tmp_path / "milestone_view.db")
    settings = AppSettings(
        current_season=2026,
        milestones_path=str(ROOT / "data" / "milestones.csv"),
    )
    manager = SettingsManager(tmp_path / "settings.json")
    milestones = load_milestones(ROOT / "data" / "milestones.csv")
    widget = MilestoneView(aggregator, milestones, settings, manager)
    yield widget
    aggregator.close()


@dataclass(frozen=True)
class FakeIssue:
    category: str
    player_id: int
    player_name: str
    stat: str
    export_value: int
    db_value: int


class FakeSnapshot:
    def as_totals_override(self) -> dict[str, list[dict]]:
        return {"batting": [], "pitching": []}


def _install_fake_importer(monkeypatch, status: str, issues=()):
    class FakeImporter:
        def __init__(self, _aggregator) -> None:
            pass

        def read_season_snapshot(self, **_kwargs):
            return FakeSnapshot()

        def validate_season_snapshot(self, _snapshot):
            return SimpleNamespace(status=status, issues=tuple(issues))

    monkeypatch.setattr(milestone_view_module, "InitialImporter", FakeImporter)


def test_final_season_button_is_direct_action_not_more_menu(view: MilestoneView) -> None:
    assert not view.final_season_button.isHidden()
    assert view.final_season_button.text()

    more_labels = [action.text() for action in view.more_menu_button.menu().actions()]
    assert view.final_season_button.text() not in more_labels
    assert more_labels == [milestone_view_module.tr("Refresh")]


def test_snapshot_issue_message_format_helpers() -> None:
    issue = FakeIssue(
        category="batting",
        player_id=101,
        player_name="C. Batter",
        stat="h",
        export_value=1,
        db_value=2,
    )

    assert (
        format_snapshot_validation_issue(issue)
        == "C. Batter · batting/h: Export 1 < boxscore 2"
    )

    validation = SimpleNamespace(issues=(issue, issue, issue))
    message = build_snapshot_incomplete_message(validation, season=2026, limit=2)
    assert "2026" in message
    assert "Showing 2 of 3 issue(s):" in message
    assert message.count("C. Batter · batting/h") == 2


def test_cancel_stops_before_reading_export_or_date(
    view: MilestoneView, monkeypatch
) -> None:
    importer_created: list[bool] = []
    date_requests: list[bool] = []

    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: False)
    monkeypatch.setattr(
        milestone_view_module,
        "InitialImporter",
        lambda _aggregator: importer_created.append(True),
    )
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: date_requests.append(True) or ("2026-12-31", True),
    )

    view._record_season_ratio_milestones()

    assert importer_created == []
    assert date_requests == []


def test_missing_export_stops_before_validation_and_date(
    view: MilestoneView, monkeypatch, tmp_path: Path
) -> None:
    warnings: list[tuple[str, str]] = []
    date_requests: list[bool] = []

    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: True)
    monkeypatch.setattr(
        view,
        "_season_export_paths",
        lambda: (
            tmp_path / "player_batting_stats.txt",
            tmp_path / "player_pitching_stats.txt",
        ),
    )
    monkeypatch.setattr(
        milestone_view_module.QMessageBox,
        "warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: date_requests.append(True) or ("2026-12-31", True),
    )

    view._record_season_ratio_milestones()

    assert warnings
    assert "player_batting_stats.txt" in warnings[0][1]
    assert date_requests == []


def test_no_current_season_stops_before_date_input(
    view: MilestoneView, monkeypatch
) -> None:
    warnings: list[tuple[str, str]] = []
    date_requests: list[bool] = []
    _install_fake_importer(monkeypatch, "no_current_season")
    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: True)
    monkeypatch.setattr(view, "_season_export_paths", lambda: (Path("bat.txt"), Path("pit.txt")))
    monkeypatch.setattr(
        milestone_view_module.QMessageBox,
        "warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: date_requests.append(True) or ("2026-12-31", True),
    )

    view._record_season_ratio_milestones()

    assert date_requests == []
    assert warnings
    assert "2026" in warnings[0][1]


def test_incomplete_snapshot_stops_before_date_input(
    view: MilestoneView, monkeypatch
) -> None:
    issue = FakeIssue("pitching", 202, "C. Pitcher", "ip_outs", 6, 9)
    warnings: list[tuple[str, str]] = []
    date_requests: list[bool] = []
    _install_fake_importer(monkeypatch, "incomplete", [issue])
    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: True)
    monkeypatch.setattr(view, "_season_export_paths", lambda: (Path("bat.txt"), Path("pit.txt")))
    monkeypatch.setattr(
        milestone_view_module.QMessageBox,
        "warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: date_requests.append(True) or ("2026-12-31", True),
    )

    view._record_season_ratio_milestones()

    assert date_requests == []
    assert warnings
    assert "C. Pitcher · pitching/ip_outs: Export 6 < boxscore 9" in warnings[0][1]


def test_complete_snapshot_requests_date_and_records(
    view: MilestoneView, monkeypatch
) -> None:
    recorded: list[tuple[int, str, dict[str, list[dict]]]] = []
    _install_fake_importer(monkeypatch, "complete")
    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: True)
    monkeypatch.setattr(view, "_season_export_paths", lambda: (Path("bat.txt"), Path("pit.txt")))
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("2026-12-31", True),
    )
    monkeypatch.setattr(view, "refresh", lambda: None)

    class FakeChecker:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check_season_ratios(self, season, *, achieved_date, totals_override):
            recorded.append((season, achieved_date, totals_override))
            return ["achievement"]

        def record_achievements(self, achievements):
            assert achievements == ["achievement"]
            return 1

    monkeypatch.setattr(milestone_view_module, "MilestoneChecker", FakeChecker)

    view._record_season_ratio_milestones()

    assert recorded == [(2026, "2026-12-31", {"batting": [], "pitching": []})]
