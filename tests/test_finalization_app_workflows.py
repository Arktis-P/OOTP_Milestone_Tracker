from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from core.config.settings_manager import AppSettings, SettingsManager
from core.import_workflow import (
    WORKFLOW_LATEST_BOXSCORES,
    load_import_workflow_state,
)
from core.milestone.message_automation.parser import parse_message
from core.milestone.message_automation.processed import (
    fingerprint_message_text,
    get_message_rescan_status,
)
from gui.app import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path: Path):
    save_path = tmp_path / "league.lg"
    boxscores = save_path / "news" / "html" / "box_scores"
    boxscores.mkdir(parents=True)
    (boxscores / "game1.html").write_text("<html></html>", encoding="utf-8")
    settings = AppSettings(
        active_save="Test League",
        active_save_path=str(save_path),
        db_path=str(tmp_path / "records.db"),
        milestones_path=str(ROOT / "data" / "milestones.csv"),
        paths={"boxscore_dir": str(boxscores)},
        current_season=2026,
    )
    manager = SettingsManager(tmp_path / "settings.json")
    widget = MainWindow(settings, manager)
    yield widget
    widget.close()


def test_source_check_advances_only_selected_persisted_workflow(window: MainWindow) -> None:
    window._check_workflow_source(WORKFLOW_LATEST_BOXSCORES)

    latest = load_import_workflow_state(
        window._aggregator.conn, WORKFLOW_LATEST_BOXSCORES
    )
    news = load_import_workflow_state(window._aggregator.conn, "news_messages")

    assert latest.current_step == "analyze_classify"
    assert latest.totals["processed"] == 1
    assert latest.started_at
    assert news.started_at is None


def test_app_message_save_returns_per_message_result_and_blocks_rescan(
    window: MainWindow,
) -> None:
    raw = (
        ROOT
        / "tests"
        / "fixtures"
        / "messages"
        / "contract_extension_01.txt"
    ).read_text(encoding="utf-8")
    parsed = parse_message(
        raw,
        tracked_teams=[],
        message_date=date(2026, 5, 1),
        season_hint=2026,
        source_id="message-finalization",
    )
    fingerprint = fingerprint_message_text(
        raw, source_id="message-finalization", source_path="fixture"
    )
    window._message_fingerprints = {"message-finalization": fingerprint}

    results: list[object] = []
    window._message_review_view = SimpleNamespace(
        finish_save=lambda rows: results.extend(rows)
    )
    window._save_approved_messages([parsed])
    worker = window._message_apply_worker
    assert worker is not None
    assert worker.wait(3000)
    QApplication.processEvents()
    window._on_message_review_saved(results)

    assert len(results) == 1
    assert results[0].source_id == "message-finalization"
    assert results[0].created_record_ids
    assert get_message_rescan_status(
        window._aggregator.conn, fingerprint
    ) == "already_applied"
