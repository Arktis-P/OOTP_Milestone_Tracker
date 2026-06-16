"""Initial stats import tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.db.meta import get_init_season_coverage
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

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
