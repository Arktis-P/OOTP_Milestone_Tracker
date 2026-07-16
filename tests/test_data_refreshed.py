"""MainWindow data_refreshed signal routing."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from core.stats.initial_import import InitImportResult
from gui.app import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    from core.config.settings_manager import SettingsManager

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(
        Path(__file__).resolve().parent.parent / "data" / "milestones.csv",
        data_dir / "milestones.csv",
    )

    settings_path = tmp_path / "settings.json"
    db_path = data_dir / "records.db"
    settings_path.write_text(
        f'{{"ootp_version":27,"current_season":2026,"db_path":"{db_path.as_posix()}",'
        f'"milestones_path":"{(data_dir / "milestones.csv").as_posix()}",'
        '"paths":{},"import_state":{}}',
        encoding="utf-8",
    )

    manager = SettingsManager(settings_path)
    settings = manager.load()

    window = MainWindow(settings=settings, settings_manager=manager)
    yield window
    window._aggregator.close()


def test_data_refreshed_routes_to_tabs(main_window: MainWindow, qapp) -> None:
    assert main_window._milestone_view is not None
    assert main_window._stats_view is not None
    assert main_window._predict_view is not None

    main_window._milestone_view.refresh = MagicMock()
    main_window._stats_view.on_data_refreshed = MagicMock()
    main_window._predict_view.on_data_refreshed = MagicMock()

    main_window.data_refreshed.emit("boxscore")
    qapp.processEvents()

    main_window._milestone_view.refresh.assert_called_once()
    main_window._stats_view.on_data_refreshed.assert_called_once_with("boxscore")
    main_window._predict_view.on_data_refreshed.assert_called_once_with("boxscore")


def test_active_initial_preview_blocks_page_rebuild_until_queued_completion(
    main_window: MainWindow, qapp, monkeypatch
) -> None:
    view = main_window._initial_import_view
    assert view is not None
    sample = (
        Path(__file__).resolve().parent.parent
        / "samples"
        / "player_stats_txt"
        / "player_batting_stats.txt"
    )
    view.batting_path.setText(str(sample))
    view.mode_first.setChecked(True)
    monkeypatch.setattr(view, "_should_persist_after_preview", MagicMock(return_value=False))
    info = MagicMock()
    monkeypatch.setattr("gui.app.QMessageBox.information", info)

    view._run_import("batting")
    assert view.has_active_operation()

    assert main_window._apply_settings_changes(main_window.settings) is False
    assert main_window._initial_import_view is view
    info.assert_called_once()

    loop = QEventLoop()
    poll = QTimer()

    def finish_when_idle() -> None:
        if not view.has_active_operation():
            loop.quit()

    poll.timeout.connect(finish_when_idle)
    poll.start(10)
    QTimer.singleShot(5_000, loop.quit)
    loop.exec()
    poll.stop()
    qapp.processEvents()

    assert not view.has_active_operation()
    assert main_window._initial_import_view is view


def test_partial_persist_result_does_not_emit_import_finished(
    main_window: MainWindow, monkeypatch
) -> None:
    view = main_window._initial_import_view
    assert view is not None
    emitted: list[bool] = []
    view.import_finished.connect(lambda: emitted.append(True))
    monkeypatch.setattr(view, "_finish_import_worker", MagicMock())
    monkeypatch.setattr(view, "_update_status", MagicMock())
    critical = MagicMock()
    monkeypatch.setattr("gui.views.initial_import_view.QMessageBox.critical", critical)

    view._on_import_finished(
        [
            InitImportResult(
                mode="first_time",
                kind="batting",
                total_scanned=10,
                saved=True,
            ),
            InitImportResult(
                mode="first_time",
                kind="pitching",
                total_scanned=10,
                errors=["file changed during import"],
                saved=False,
            ),
        ]
    )

    assert emitted == []
    critical.assert_called_once()
