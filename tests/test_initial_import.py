"""Initial stats import tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "test.db")
    yield agg
    agg.close()


def test_import_batting_skips_non_overall_split(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    result = importer.import_batting(SAMPLES_STATS / "player_batting_stats.txt")
    assert result.imported == 2
    assert result.skipped >= 1

    row = aggregator.conn.execute(
        "SELECT hr FROM career_batting_init WHERE player_id = ? AND season = ?",
        (28987, 2025),
    ).fetchone()
    assert row is not None
    assert row["hr"] == 499


def test_import_pitching(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    result = importer.import_pitching(SAMPLES_STATS / "player_pitching_stats.txt")
    assert result.imported == 1

    row = aggregator.conn.execute(
        "SELECT ip_outs, cg, sho FROM career_pitching_init WHERE player_id = ?",
        (50432,),
    ).fetchone()
    assert row is not None
    assert row["ip_outs"] == 195
    assert row["cg"] == 2
    assert row["sho"] == 1


def test_career_totals_include_init(aggregator: Aggregator) -> None:
    importer = InitialImporter(aggregator)
    importer.import_batting(SAMPLES_STATS / "player_batting_stats.txt")

    career = aggregator.get_batting_career(28987)
    assert career is not None
    assert career["career_hr"] == 499
