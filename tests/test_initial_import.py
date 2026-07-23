"""Initial stats import tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from core.db.meta import get_init_season_coverage
from core.stats.aggregator import Aggregator
from core.stats.initial_import import (
    ExportFileEmptyError,
    ExportFileMissingError,
    InitialImporter,
    SeasonExportSnapshot,
)
from gui.workers.initial_import_worker import InitialImportWorker

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "test.db")
    yield agg
    agg.close()


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


def test_read_season_snapshot_uses_export_totals_without_writing_db(
    aggregator: Aggregator,
) -> None:
    snapshot = InitialImporter(aggregator).read_season_snapshot_dir(
        SAMPLES_STATS, season=2025
    )

    batting = {row["player_id"]: row for row in snapshot.batting}
    pitching = {row["player_id"]: row for row in snapshot.pitching}
    assert batting[151]["ab"] == 70
    assert batting[151]["hr"] == 5
    assert batting[151]["avg"] == pytest.approx(0.314)
    assert pitching[50432]["era"] == pytest.approx(3.05)
    assert snapshot.as_totals_override().keys() == {"batting", "pitching"}

    assert (
        aggregator.conn.execute("SELECT COUNT(*) FROM career_batting_init").fetchone()[0]
        == 0
    )
    assert (
        aggregator.conn.execute("SELECT COUNT(*) FROM career_pitching_init").fetchone()[0]
        == 0
    )


def test_read_season_snapshot_reports_missing_and_empty_exports(
    aggregator: Aggregator, tmp_path: Path
) -> None:
    importer = InitialImporter(aggregator)
    with pytest.raises(ExportFileMissingError):
        importer.read_season_snapshot_dir(tmp_path / "missing", season=2026)

    empty = tmp_path / "player_batting_stats.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ExportFileEmptyError):
        importer.read_season_snapshot(season=2026, batting_path=empty)


def _insert_current_season_boxscore_totals(aggregator: Aggregator) -> None:
    aggregator.conn.executemany(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (?, ?, ?)",
        [
            (101, "Complete Batter", "C. Batter"),
            (202, "Complete Pitcher", "C. Pitcher"),
        ],
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings, is_mlb
        ) VALUES (7001, '2026-04-01', 2026, 'Away', 'Home', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, r, rbi, bb, k,
            doubles, triples, home_runs, stolen_bases, hit_by_pitch
        ) VALUES (7001, 101, 2026, 'Home', '2026-04-01', 4, 2, 1, 3, 1, 1, 1, 0, 1, 1, 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, h, er, bb, k, hr,
            win, loss, save, is_starter, hold
        ) VALUES (7001, 202, 2026, 'Home', '2026-04-01', 9, 2, 1, 1, 5, 1, 1, 0, 1, 1, 1)
        """
    )
    aggregator.conn.commit()


def _complete_snapshot(**overrides: dict[str, int]) -> SeasonExportSnapshot:
    batting = {
        "player_id": 101,
        "name": "C. Batter",
        "ab": 4,
        "h": 2,
        "r": 1,
        "rbi": 3,
        "bb": 1,
        "hbp": 1,
        "k": 1,
        "hr": 1,
        "sb": 1,
        "doubles": 1,
        "triples": 0,
    }
    pitching = {
        "player_id": 202,
        "name": "C. Pitcher",
        "ip_outs": 9,
        "h": 2,
        "er": 1,
        "bb": 1,
        "k": 5,
        "hr": 1,
        "w": 1,
        "l": 0,
        "sv": 1,
        "gs": 1,
        "holds": 1,
    }
    batting.update(overrides.get("batting", {}))
    pitching.update(overrides.get("pitching", {}))
    return SeasonExportSnapshot(
        season=2026,
        batting=(batting,),
        pitching=(pitching,),
        kinds=("batting", "pitching"),
    )


def test_validate_season_snapshot_reports_no_current_season(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    result = InitialImporter(aggregator).validate_season_snapshot(
        SeasonExportSnapshot(season=2026, kinds=("batting", "pitching"))
    )
    assert result.status == "no_current_season"
    assert result.issues == ()


def test_validate_season_snapshot_complete_export(aggregator: Aggregator) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    result = InitialImporter(aggregator).validate_season_snapshot(_complete_snapshot())
    assert result.status == "complete"
    assert result.issues == ()


def test_validate_season_snapshot_allows_export_values_greater_than_db(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    snapshot = _complete_snapshot(
        batting={"ab": 6, "h": 4, "hr": 2},
        pitching={"ip_outs": 12, "k": 7, "sv": 2},
    )
    result = InitialImporter(aggregator).validate_season_snapshot(snapshot)
    assert result.status == "complete"
    assert result.issues == ()


def test_validate_season_snapshot_reports_lower_export_field(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    result = InitialImporter(aggregator).validate_season_snapshot(
        _complete_snapshot(batting={"h": 1})
    )
    assert result.status == "incomplete"
    assert [issue.stat for issue in result.issues] == ["h"]
    assert result.issues[0].category == "batting"
    assert result.issues[0].player_id == 101
    assert result.issues[0].player_name == "C. Batter"
    assert result.issues[0].export_value == 1
    assert result.issues[0].db_value == 2


def test_validate_season_snapshot_compares_hit_by_pitch(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    result = InitialImporter(aggregator).validate_season_snapshot(
        _complete_snapshot(batting={"hbp": 0})
    )

    assert result.status == "incomplete"
    issue = next(issue for issue in result.issues if issue.stat == "hbp")
    assert issue.export_value == 0
    assert issue.db_value == 1


def test_validate_season_snapshot_reports_missing_player_row_as_zero(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    other_batter = {
        **_complete_snapshot().batting[0],
        "player_id": 999,
        "name": "Other Batter",
    }
    snapshot = SeasonExportSnapshot(
        season=2026,
        batting=(other_batter,),
        pitching=_complete_snapshot().pitching,
        kinds=("batting", "pitching"),
    )
    result = InitialImporter(aggregator).validate_season_snapshot(snapshot)
    assert result.status == "incomplete"
    batting_stats = {issue.stat for issue in result.issues if issue.category == "batting"}
    assert {"ab", "h", "r", "rbi", "bb", "k", "hr", "sb", "doubles"} <= batting_stats
    assert all(issue.export_value == 0 for issue in result.issues if issue.category == "batting")


def test_validate_season_snapshot_both_files_require_rows_for_both_categories(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    snapshot = SeasonExportSnapshot(
        season=2026,
        batting=_complete_snapshot().batting,
        pitching=(),
        kinds=("batting", "pitching"),
    )
    result = InitialImporter(aggregator).validate_season_snapshot(snapshot)
    assert result.status == "no_current_season"
    assert result.issues == ()


def test_validate_season_snapshot_batting_only_and_pitching_only_missing_behavior(
    aggregator: Aggregator,
) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    complete = _complete_snapshot()
    importer = InitialImporter(aggregator)

    batting_only = SeasonExportSnapshot(
        season=2026,
        batting=complete.batting,
        pitching=(),
        kinds=("batting",),
    )
    pitching_only = SeasonExportSnapshot(
        season=2026,
        batting=(),
        pitching=complete.pitching,
        kinds=("pitching",),
    )

    batting_only_result = importer.validate_season_snapshot(batting_only)
    pitching_only_result = importer.validate_season_snapshot(pitching_only)

    assert batting_only_result.status == "incomplete"
    assert {issue.category for issue in batting_only_result.issues} == {"pitching"}
    assert pitching_only_result.status == "incomplete"
    assert {issue.category for issue in pitching_only_result.issues} == {"batting"}


def test_validate_season_snapshot_export_without_db_totals_is_complete(
    aggregator: Aggregator,
) -> None:
    result = InitialImporter(aggregator).validate_season_snapshot(_complete_snapshot())
    assert result.status == "complete"
    assert result.issues == ()


def test_validate_season_snapshot_does_not_mutate_db(aggregator: Aggregator) -> None:
    _insert_current_season_boxscore_totals(aggregator)
    before = {
        table: aggregator.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("players", "games", "batting_logs", "pitching_logs")
    }
    InitialImporter(aggregator).validate_season_snapshot(_complete_snapshot(batting={"h": 1}))
    after = {
        table: aggregator.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert after == before


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
