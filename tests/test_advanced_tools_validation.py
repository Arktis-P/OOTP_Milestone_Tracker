from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings
from gui.views.advanced_tools_view import AdvancedToolsView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSettingsManager:
    def ensure_derived_paths(self, settings):
        return settings

    def save(self, settings):
        self.saved = settings


def _settings(tmp_path: Path) -> AppSettings:
    save = tmp_path / "Test.lg"
    save.mkdir()
    boxscores = save / "news" / "html" / "box_scores"
    boxscores.mkdir(parents=True)
    milestones = tmp_path / "milestones.csv"
    milestones.write_text("key,label,stat,threshold,scope,category,direction,grade\n", encoding="utf-8")
    return AppSettings(
        active_save="Test.lg",
        active_save_path=str(save),
        current_season=2026,
        tracked_teams=["SEA"],
        db_path=str(tmp_path / "live_records.db"),
        paths={"boxscore_dir": str(boxscores)},
        milestones_path=str(milestones),
    )


def test_season_validation_config_targets_validation_db_not_live_db(qapp, tmp_path) -> None:
    view = AdvancedToolsView(FakeSettingsManager(), _settings(tmp_path))
    try:
        config = view._build_season_validation_config()
        assert "validation" in [part.lower() for part in config.target_db.parts]
        assert config.target_db.name == "records.db"
        assert config.target_db != config.live_db
        assert config.reset is True
        assert config.dry_run is False
    finally:
        view.deleteLater()


def test_season_validation_ui_makes_non_operating_db_scope_visible(qapp, tmp_path) -> None:
    view = AdvancedToolsView(FakeSettingsManager(), _settings(tmp_path))
    try:
        assert view.season_validation_button.isEnabled()
        assert "validation DB" in view.validation_status_label.text()
        assert "not modified" in view.validation_status_label.text()
    finally:
        view.deleteLater()

def test_season_validation_error_remains_on_page(qapp, tmp_path) -> None:
    view = AdvancedToolsView(FakeSettingsManager(), _settings(tmp_path))
    try:
        view._on_season_validation_error("boom")
        assert view.season_validation_button.isEnabled()
        assert "not modified" in view.validation_status_label.text()
        assert view.validation_report_label.text() == "boom"
    finally:
        view.deleteLater()
