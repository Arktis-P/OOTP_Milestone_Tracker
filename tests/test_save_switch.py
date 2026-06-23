"""Save switch reloads the correct per-save database."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from core.config.save_db import resolve_save_db_path
from core.config.settings_manager import AppSettings, SettingsManager
from core.db.schema import init_database
from core.stats.aggregator import Aggregator
from gui.app import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def save_switch_window(qapp, tmp_path, monkeypatch):
    import core.config.paths as paths

    user_dir = tmp_path / "userdata"
    user_dir.mkdir()
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(paths, "_USER_DATA_READY", True)

    shutil.copy(
        Path(__file__).resolve().parent.parent / "data" / "milestones.csv",
        user_dir / "milestones.csv",
    )

    save_a = tmp_path / "SaveA.lg"
    save_b = tmp_path / "SaveB.lg"
    save_a.mkdir()
    save_b.mkdir()

    db_a = resolve_save_db_path(save_a)
    db_b = resolve_save_db_path(save_b)
    init_database(db_a)
    init_database(db_b)

    with Aggregator(db_a) as agg:
        agg.conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope,
                season, achieved_date, achieved_value
            ) VALUES (1, 'test', '테스트', 'game', 2026, '2026-01-01', 1)
            """
        )
        agg.conn.commit()

    settings_path = tmp_path / "settings.json"
    manager = SettingsManager(settings_path)
    settings = manager.update_active_save(
        AppSettings(),
        save_root=str(tmp_path),
        save_name="SaveA",
        save_path=str(save_a),
    )
    settings.milestones_path = str(user_dir / "milestones.csv")
    manager.save(settings)

    window = MainWindow(settings=settings, settings_manager=manager)
    yield window, manager, save_a, save_b
    window._aggregator.close()


def test_apply_settings_switches_milestone_records(save_switch_window, qapp) -> None:
    window, manager, save_a, save_b = save_switch_window
    assert window._milestone_view is not None
    assert len(window._aggregator.get_recent_milestone_records(10)) == 1

    updated = manager.update_active_save(
        window.settings,
        save_root=str(save_a.parent),
        save_name="SaveB",
        save_path=str(save_b),
    )
    updated.milestones_path = window.settings.milestones_path
    manager.save(updated)

    window._apply_settings_changes(updated)
    qapp.processEvents()

    assert window._aggregator.db_path.resolve() == resolve_save_db_path(save_b).resolve()
    assert len(window._aggregator.get_recent_milestone_records(10)) == 0
    assert window._milestone_view is not None
