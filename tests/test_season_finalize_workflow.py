"""Season-finalization result contract for workflow integration."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.import_workflow import (
    OUTCOME_COMPLETED,
    WORKFLOW_SEASON_FINALIZE,
    load_import_workflow_state,
)
from core.i18n import get_language, set_language
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.stats.aggregator import Aggregator
from gui.views import milestone_view as milestone_view_module
from gui.views.milestone_view import (
    SEASON_FINALIZE_OUTCOME_CANCELLED,
    SEASON_FINALIZE_OUTCOME_COMPLETED,
    SEASON_FINALIZE_OUTCOME_FAILED,
    SEASON_FINALIZE_OUTCOME_PARTIAL_SUCCESS,
    SEASON_FINALIZE_SOURCE,
    MilestoneView,
    SeasonFinalizeResult,
)
from gui.app import MainWindow

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


class FakeSnapshot:
    def __init__(self, totals_override: dict[str, list[dict]] | None = None) -> None:
        self._totals_override = totals_override or {"batting": [], "pitching": []}

    def as_totals_override(self) -> dict[str, list[dict]]:
        return self._totals_override


def _install_importer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str = "complete",
    snapshot: FakeSnapshot | None = None,
    issues: tuple[object, ...] = (),
) -> None:
    class FakeImporter:
        def __init__(self, _aggregator) -> None:
            pass

        def read_season_snapshot(self, **_kwargs):
            return snapshot or FakeSnapshot()

        def validate_season_snapshot(self, _snapshot):
            return SimpleNamespace(status=status, issues=issues)

    monkeypatch.setattr(milestone_view_module, "InitialImporter", FakeImporter)


@pytest.fixture
def view(qapp, tmp_path: Path):
    aggregator = Aggregator(tmp_path / "season_finalize.db")
    settings = AppSettings(
        current_season=2026,
        milestones_path=str(ROOT / "data" / "milestones.csv"),
    )
    manager = SettingsManager(tmp_path / "settings.json")
    milestone = MilestoneDefinition(
        key="season_avg_350_contract",
        label="Season AVG .350",
        stat="season_avg",
        threshold=0.350,
        scope="season_ratio",
        category="batting",
    )
    widget = MilestoneView(
        aggregator,
        MilestoneDefinitions(batting=[milestone], pitching=[]),
        settings,
        manager,
    )
    yield widget
    aggregator.close()


def _prepare_success_path(view: MilestoneView, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: True)
    monkeypatch.setattr(view, "_season_export_paths", lambda: (Path("bat.txt"), Path("pit.txt")))
    monkeypatch.setattr(
        milestone_view_module.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("2026-12-31", True),
    )
    monkeypatch.setattr(view, "refresh", lambda: None)


def test_completed_result_counts_created_then_duplicate_rerun(
    view: MilestoneView, monkeypatch: pytest.MonkeyPatch
) -> None:
    view.aggregator.upsert_player(8101, "Export Batter", "E. Batter")
    _prepare_success_path(view, monkeypatch)
    _install_importer(
        monkeypatch,
        snapshot=FakeSnapshot(
            {
                "batting": [
                    {
                        "id": 8101,
                        "player_id": 8101,
                        "name": "E. Batter",
                        "team": "NYY",
                        "ab": 502,
                        "avg": 0.361,
                    }
                ],
                "pitching": [],
            }
        ),
    )

    first = view._record_season_ratio_milestones()
    second = view._record_season_ratio_milestones()

    assert first.outcome == SEASON_FINALIZE_OUTCOME_COMPLETED
    assert first.season == 2026
    assert first.processed == 1
    assert first.created == 1
    assert first.duplicates == 0
    assert first.source == SEASON_FINALIZE_SOURCE
    assert second.outcome == SEASON_FINALIZE_OUTCOME_COMPLETED
    assert second.processed == 1
    assert second.created == 0
    assert second.duplicates == 1
    row = view.aggregator.conn.execute(
        """
        SELECT COUNT(*) FROM milestone_records
        WHERE milestone_key = 'season_avg_350_contract'
          AND source = ?
          AND season = 2026
        """,
        (SEASON_FINALIZE_SOURCE,),
    ).fetchone()
    assert row[0] == 1


def test_user_cancel_returns_cancelled_and_emits_signal(
    view: MilestoneView, monkeypatch: pytest.MonkeyPatch
) -> None:
    emitted: list[object] = []
    view.season_finalize_finished.connect(emitted.append)
    monkeypatch.setattr(view, "_confirm_season_ratio_export", lambda *_args: False)

    result = view._record_season_ratio_milestones()

    assert result.outcome == SEASON_FINALIZE_OUTCOME_CANCELLED
    assert result.processed == 0
    assert result.created == 0
    assert emitted == [result]


def test_validation_problem_returns_failed(
    view: MilestoneView, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings: list[tuple[str, str]] = []
    _prepare_success_path(view, monkeypatch)
    _install_importer(monkeypatch, status="no_current_season")
    monkeypatch.setattr(
        milestone_view_module.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    result = view._record_season_ratio_milestones()

    assert result.outcome == SEASON_FINALIZE_OUTCOME_FAILED
    assert result.errors == 1
    assert result.unresolved == {"errors": 1}
    assert result.source == SEASON_FINALIZE_SOURCE
    assert warnings


def test_partial_save_error_returns_partial_success(
    view: MilestoneView, monkeypatch: pytest.MonkeyPatch
) -> None:
    created_after_error = {"count": 0}
    _prepare_success_path(view, monkeypatch)
    _install_importer(monkeypatch)
    monkeypatch.setattr(
        view,
        "_season_finalize_record_count",
        lambda _season: created_after_error["count"],
    )
    monkeypatch.setattr(
        milestone_view_module.QMessageBox,
        "warning",
        lambda *_args: None,
    )

    class FakeChecker:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check_season_ratios(self, *_args, **_kwargs):
            return [object(), object()]

        def record_achievements(self, _achievements):
            created_after_error["count"] = 1
            raise RuntimeError("one row failed")

    monkeypatch.setattr(milestone_view_module, "MilestoneChecker", FakeChecker)

    result = view._record_season_ratio_milestones()

    assert result.outcome == SEASON_FINALIZE_OUTCOME_PARTIAL_SUCCESS
    assert result.processed == 2
    assert result.created == 1
    assert result.duplicates == 1
    assert result.errors == 1
    assert result.unresolved == {"errors": 1}


def test_main_window_persists_zero_new_duplicate_rerun_as_completed(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        current_season=2026,
        db_path=str(tmp_path / "app.db"),
        milestones_path=str(ROOT / "data" / "milestones.csv"),
    )
    window = MainWindow(settings, SettingsManager(tmp_path / "app-settings.json"))
    try:
        result = SeasonFinalizeResult(
            outcome=OUTCOME_COMPLETED,
            season=2026,
            processed=1,
            created=0,
            duplicates=1,
            message="already finalized",
        )
        monkeypatch.setattr(
            window._milestone_view,
            "_record_season_ratio_milestones",
            lambda: result,
        )

        window._run_season_finalize_workflow()

        state = load_import_workflow_state(
            window._aggregator.conn, WORKFLOW_SEASON_FINALIZE
        )
        assert state.outcome == OUTCOME_COMPLETED
        assert state.totals["season"] == 2026
        assert state.totals["created"] == 0
        assert state.totals["duplicates"] == 1
    finally:
        window.close()
