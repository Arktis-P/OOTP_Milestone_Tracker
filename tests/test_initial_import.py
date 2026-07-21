"""Initial stats import tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings, SettingsManager
from core.db.meta import get_init_season_coverage
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter, InitImportResult
from gui.workers.initial_import_worker import InitialImportWorker

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "test.db")
    yield agg
    agg.close()


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_first_time_uses_first_column_player_id(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    result = importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    assert result.inserted >= 3
    assert result.skipped == 0

    row = aggregator.conn.execute(
        "SELECT hr FROM career_batting_init WHERE player_id = ? AND season = ?",
        (28987, 2025),
    ).fetchone()
    assert row is not None
    assert row["hr"] == 499

    minor = aggregator.conn.execute(
        "SELECT 1 FROM career_batting_init WHERE player_id = ?", (999,)
    ).fetchone()
    assert minor is None

    coverage = get_init_season_coverage(aggregator.conn)
    assert coverage == 2025


def test_trade_aggregation_connor_joe(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    row = aggregator.conn.execute(
        "SELECT ab, hr FROM career_batting_init WHERE player_id = ? AND season = ?",
        (151, 2025),
    ).fetchone()
    assert row is not None
    assert row["ab"] == 70
    assert row["hr"] == 5


def test_first_time_excludes_current_season(aggregator: Aggregator) -> None:
    from core.stats.initial_import import BATTING_COLS

    importer = InitialImporter(aggregator)
    rows = importer._parse_file(SAMPLES_STATS / "player_batting_stats.txt", BATTING_COLS)
    rows.append({
        **rows[0],
        "player_id": 5555,
        "season": 2026,
        "hr": 99,
        "league_level_id": 1,
        "split_id": 1,
    })
    aggregated = importer._filter_and_aggregate(rows, season_filter="lt", current_season=2026)
    assert (5555, 2026) not in aggregated


def test_import_pitching(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    result = importer.import_pitching(
        SAMPLES_STATS / "player_pitching_stats.txt",
        "first_time",
        current_season=2026,
    )
    assert result.inserted == 1

    row = aggregator.conn.execute(
        "SELECT ip_outs, cg, sho FROM career_pitching_init WHERE player_id = ?",
        (50432,),
    ).fetchone()
    assert row is not None
    assert row["ip_outs"] == 195
    assert row["cg"] == 2
    assert row["sho"] == 1


def test_career_totals_respect_season_coverage(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )

    career = aggregator.get_batting_career(28987)
    assert career is not None
    assert career["career_hr"] == 499

    data = __import__("core.parser.boxscore_html", fromlist=["BoxscoreHTMLParser"]).BoxscoreHTMLParser(
        ROOT / "samples" / "boxscore_html" / "game_box_13.html"
    ).parse()
    aggregator.import_boxscore(data, season=2026)

    career_after = aggregator.get_batting_career(28987)
    assert career_after is not None
    assert career_after["career_hr"] == 500  # init 499 + boxscore 1


def test_refresh_persist_batting_then_pitching_same_connection(
    aggregator: Aggregator,
) -> None:
    """Worker imports batting then pitching on one connection (compare leaves implicit tx)."""
    importer = InitialImporter(aggregator)
    season = 2026
    importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        season,
    )
    importer.import_pitching(
        SAMPLES_STATS / "player_pitching_stats.txt",
        "first_time",
        season,
    )
    parser = __import__(
        "core.parser.boxscore_html", fromlist=["BoxscoreHTMLParser"]
    ).BoxscoreHTMLParser(ROOT / "samples" / "boxscore_html" / "game_box_13.html")
    aggregator.import_boxscore(parser.parse(), season=2025)

    batting = importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "refresh",
        season,
        persist=True,
    )
    pitching = importer.import_pitching(
        SAMPLES_STATS / "player_pitching_stats.txt",
        "refresh",
        season,
        persist=True,
    )
    assert batting.saved
    assert pitching.saved


def test_refresh_mode_compare_only_preview(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    data = __import__("core.parser.boxscore_html", fromlist=["BoxscoreHTMLParser"]).BoxscoreHTMLParser(
        ROOT / "samples" / "boxscore_html" / "game_box_13.html"
    ).parse()
    aggregator.import_boxscore(data, season=2025)

    preview = importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "refresh",
        current_season=2026,
        persist=False,
    )
    assert preview.saved is False
    assert isinstance(preview.diffs, list)


def test_init_only_season_stats_without_boxscore(aggregator: Aggregator) -> None:
    """Stats 파일만 있어도 시즌·선수 목록을 볼 수 있다."""
    importer = InitialImporter(aggregator)
    importer.import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    importer.import_pitching(
        SAMPLES_STATS / "player_pitching_stats.txt",
        "first_time",
        current_season=2026,
    )

    seasons = aggregator.get_available_seasons()
    assert 2025 in seasons

    batting = aggregator.get_batting_season(28987, 2025)
    assert batting is not None
    assert batting["_source"] == "init"
    assert batting["hr"] == 499

    pitching = aggregator.get_pitching_season(50432, 2025)
    assert pitching is not None
    assert pitching["_source"] == "init"
    assert pitching["ip_outs"] == 195

    players = aggregator.get_tracked_players()
    player_ids = {p["player_id"] for p in players}
    assert 28987 in player_ids
    assert 50432 in player_ids


def test_preview_worker_uses_snapshot_and_leaves_live_db_unchanged(
    aggregator: Aggregator,
) -> None:
    before = {
        table: aggregator.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "career_batting_init",
            "players",
            "player_roster",
            "player_team_affiliations",
        )
    }
    completed: list[object] = []
    errors: list[str] = []
    worker = InitialImportWorker(
        aggregator.db_path,
        batting_path=str(SAMPLES_STATS / "player_batting_stats.txt"),
        pitching_path=None,
        mode="first_time",
        current_season=2026,
        persist=False,
    )
    worker.completed.connect(completed.append, Qt.ConnectionType.DirectConnection)
    worker.error.connect(errors.append, Qt.ConnectionType.DirectConnection)

    worker.start()
    assert worker.wait(5_000)

    assert errors == []
    assert completed
    results = completed[0]
    assert isinstance(results, list)
    assert results[0].total_scanned > 0
    after = {
        table: aggregator.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert after == before


def test_initial_import_worker_cancels_between_files(
    aggregator: Aggregator, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = InitialImportWorker(
        aggregator.db_path,
        batting_path=str(SAMPLES_STATS / "player_batting_stats.txt"),
        pitching_path=str(SAMPLES_STATS / "player_pitching_stats.txt"),
        mode="first_time",
        current_season=2026,
        persist=False,
    )

    def fake_batting(self, path, mode, current_season, *, persist=True):
        worker.cancel()
        return InitImportResult(
            mode=mode,
            kind="batting",
            total_scanned=1,
            saved=persist,
        )

    def fake_pitching(self, path, mode, current_season, *, persist=True):
        raise AssertionError("pitching import should not start after cancellation")

    monkeypatch.setattr(InitialImporter, "import_batting", fake_batting)
    monkeypatch.setattr(InitialImporter, "import_pitching", fake_pitching)

    completed: list[object] = []
    cancelled: list[tuple[str, object]] = []
    errors: list[str] = []
    worker.completed.connect(completed.append, Qt.ConnectionType.DirectConnection)
    worker.cancelled.connect(
        lambda message, results: cancelled.append((message, results)),
        Qt.ConnectionType.DirectConnection,
    )
    worker.error.connect(errors.append, Qt.ConnectionType.DirectConnection)

    worker.start()
    assert worker.wait(5_000)

    assert completed == []
    assert errors == []
    assert cancelled
    message, results = cancelled[0]
    assert "cancelled" in message.lower()
    assert isinstance(results, list)
    assert [result.kind for result in results] == ["batting"]


def test_initial_import_view_cancel_and_retry_preserve_payload(
    qapp: QApplication, aggregator: Aggregator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gui.views.initial_import_view import InitialImportView

    settings = AppSettings(current_season=2026)
    settings_manager = SettingsManager(tmp_path / "settings.json")
    view = InitialImportView(aggregator, settings, settings_manager)
    payload = {
        "batting_path": str(SAMPLES_STATS / "player_batting_stats.txt"),
        "pitching_path": str(SAMPLES_STATS / "player_pitching_stats.txt"),
        "mode": "first_time",
        "season": 2026,
    }
    view._pending_import = dict(payload)

    started_payloads: list[dict] = []

    def fake_start_preview() -> None:
        assert view._pending_import is not None
        started_payloads.append(dict(view._pending_import))

    monkeypatch.setattr(view, "_start_preview_worker", fake_start_preview)
    view._set_retry_available(True)
    assert not view.retry_button.isHidden()
    assert view.retry_button.isEnabled()

    view._retry_pending_import()
    assert started_payloads == [payload]
    assert view._pending_import == payload

    class DummyWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    dummy = DummyWorker()
    view._active_stage = "preview"
    view._preview_worker = dummy  # type: ignore[assignment]
    view.cancel_button.setVisible(True)
    view.cancel_button.setEnabled(True)

    view._cancel_operation()

    assert dummy.cancelled is True
    assert view.cancel_button.isEnabled() is False
    assert not view.progress_label.isHidden()
    assert view._pending_import == payload
