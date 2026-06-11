"""MainWindow data_refreshed signal routing."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

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
