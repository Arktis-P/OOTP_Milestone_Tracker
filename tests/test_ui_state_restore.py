"""UI state persistence and per-save restore tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from core.config.save_db import resolve_save_db_path
from core.config.settings_manager import AppSettings, SettingsManager, save_ui_state_key
from core.db.schema import init_database
from gui.app import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _prepare_user_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import core.config.paths as paths

    user_dir = tmp_path / "userdata"
    user_dir.mkdir()
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(paths, "_USER_DATA_READY", True)
    shutil.copy(
        Path(__file__).resolve().parent.parent / "data" / "milestones.csv",
        user_dir / "milestones.csv",
    )
    return user_dir


def _make_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    save_name: str = "SaveA",
) -> tuple[SettingsManager, AppSettings, Path]:
    user_dir = _prepare_user_dir(tmp_path, monkeypatch)
    save_path = tmp_path / f"{save_name}.lg"
    save_path.mkdir()
    init_database(resolve_save_db_path(save_path))
    manager = SettingsManager(tmp_path / "settings.json")
    settings = manager.update_active_save(
        AppSettings(),
        save_root=str(tmp_path),
        save_name=save_name,
        save_path=str(save_path),
    )
    settings.current_season = 2026
    settings.milestones_path = str(user_dir / "milestones.csv")
    return manager, settings, save_path


def test_settings_ui_state_round_trips_and_defaults(tmp_path: Path) -> None:
    manager = SettingsManager(tmp_path / "settings.json")
    settings = AppSettings()
    settings.ui_state = {
        "global": {"last_page_index": 2, "geometry": "abc"},
        "saves": {"key": {"stats": {"mode": "career"}}},
    }

    manager.save(settings)
    loaded = manager.load()

    assert loaded.ui_state["global"]["last_page_index"] == 2
    assert loaded.ui_state["saves"]["key"]["stats"]["mode"] == "career"

    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text('{"current_season": 2026}\n', encoding="utf-8")
    legacy = SettingsManager(legacy_path).load()
    assert legacy.ui_state == {"global": {}, "saves": {}}


def test_save_ui_state_key_is_stable_and_not_raw_path(tmp_path: Path) -> None:
    save_path = tmp_path / "League.lg"
    save_path.mkdir()

    key = save_ui_state_key(str(save_path))

    assert key == save_ui_state_key(str(save_path.resolve()))
    assert str(save_path) not in key
    assert len(key) == 24


def test_main_window_restores_global_page_and_stats_state(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, settings, save_path = _make_settings(tmp_path, monkeypatch)
    key = save_ui_state_key(str(save_path))
    settings.ui_state = {
        "global": {"last_page_index": 2, "geometry": "not-valid-base64"},
        "saves": {
            key: {
                "stats": {
                    "splitter_sizes": [310, 690],
                    "mode": "career",
                    "season": 2026,
                }
            }
        },
    }

    window = MainWindow(settings=settings, settings_manager=manager)
    try:
        assert window._stack.currentIndex() == 2
        assert window._sidebar.current_index() == 2
        assert window._stats_view is not None
        assert window._stats_view.export_ui_state()["mode"] == "career"
        assert window._stats_view.season_combo.currentData() == 2026
        assert window.width() >= window.minimumWidth()
        assert window.height() >= window.minimumHeight()
    finally:
        window._aggregator.close()


def test_stats_state_is_isolated_by_save_on_switch(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, settings, save_a = _make_settings(tmp_path, monkeypatch, "SaveA")
    save_b = tmp_path / "SaveB.lg"
    save_b.mkdir()
    init_database(resolve_save_db_path(save_b))
    key_a = save_ui_state_key(str(save_a))
    key_b = save_ui_state_key(str(save_b))
    settings.ui_state = {
        "global": {"last_page_index": 2},
        "saves": {
            key_a: {"stats": {"splitter_sizes": [250, 750], "mode": "career", "season": 2026}},
            key_b: {"stats": {"splitter_sizes": [420, 580], "mode": "postseason", "season": 2026}},
        },
    }
    window = MainWindow(settings=settings, settings_manager=manager)
    try:
        assert window._stats_view is not None
        assert window._stats_view.export_ui_state()["mode"] == "career"

        updated = manager.update_active_save(
            window.settings,
            save_root=str(tmp_path),
            save_name="SaveB",
            save_path=str(save_b),
        )
        updated.milestones_path = window.settings.milestones_path
        assert window._apply_settings_changes(updated)
        qapp.processEvents()

        assert window._stats_view is not None
        assert window._stats_view.export_ui_state()["mode"] == "postseason"
        assert window.settings.ui_state["saves"][key_a]["stats"]["mode"] == "career"
    finally:
        window._aggregator.close()


def test_stats_restore_ignores_corrupt_values_and_falls_back(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, settings, save_path = _make_settings(tmp_path, monkeypatch)
    key = save_ui_state_key(str(save_path))
    settings.ui_state = {
        "global": {"last_page_index": 99},
        "saves": {
            key: {
                "stats": {
                    "splitter_sizes": ["bad", -1],
                    "mode": "bad-mode",
                    "season": 1901,
                }
            }
        },
    }

    window = MainWindow(settings=settings, settings_manager=manager)
    try:
        assert window._stack.currentIndex() == 0
        assert window._stats_view is not None
        state = window._stats_view.export_ui_state()
        assert state["mode"] == "season"
        assert state["season"] == 2026
    finally:
        window._aggregator.close()


def test_restore_geometry_falls_back_when_saved_frame_is_offscreen(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, settings, _save_path = _make_settings(tmp_path, monkeypatch)
    settings.ui_state = {"global": {"geometry": "pretend-valid"}, "saves": {}}
    window = MainWindow(settings=settings, settings_manager=manager)
    try:
        def fake_restore_geometry(_payload):
            window.setGeometry(QRect(999_000, 999_000, 900, 600))
            return True

        monkeypatch.setattr(window, "restoreGeometry", fake_restore_geometry)
        window._restore_ui_state()

        screens = QApplication.screens()
        if screens:
            assert any(
                window.frameGeometry().intersects(screen.availableGeometry())
                for screen in screens
            )
        assert window.width() >= window.minimumWidth()
        assert window.height() >= window.minimumHeight()
    finally:
        window._aggregator.close()
