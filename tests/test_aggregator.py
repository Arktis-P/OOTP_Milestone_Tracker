"""Aggregator and batting notes tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.parser.batting_notes import get_player_event_counts
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import ip_to_outs, outs_to_ip_str

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_records.db"


@pytest.fixture
def aggregator(db_path: Path) -> Aggregator:
    agg = Aggregator(db_path)
    yield agg
    agg.close()


def test_ip_conversion() -> None:
    assert ip_to_outs("2.1") == 7
    assert ip_to_outs("4.0") == 12
    assert ip_to_outs("0.2") == 2
    assert outs_to_ip_str(7) == "2.1"


def test_batting_notes_counts() -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    grichuk = get_player_event_counts(data.away_batting_notes, "R. Grichuk")
    assert grichuk.home_runs == 1

    lee = get_player_event_counts(data.home_batting_notes, "J. Lee")
    assert lee.doubles == 1
    assert lee.home_runs == 1
    assert lee.stolen_bases == 1

    mcmahon = get_player_event_counts(data.away_batting_notes, "R. McMahon")
    assert mcmahon.gidp == 1

    game20 = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
    tucker = get_player_event_counts(game20.home_batting_notes, "K. Tucker")
    assert tucker.home_runs == 1

    from core.parser.batting_notes import parse_team_batting_notes

    sb_counts = parse_team_batting_notes("BATTING\nSB:\nJ. Lee 3 (15)\n")
    assert sb_counts["J. Lee"].stolen_bases == 3

    hr_counts = parse_team_batting_notes(
        "BATTING\nHome Runs:\nR. Grichuk 2 (5, 6th Inning off P. Blackburn, 1 on, 1 out)\n"
    )
    assert hr_counts["R. Grichuk"].home_runs == 2


def test_import_boxscore(aggregator: Aggregator) -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    result = aggregator.import_boxscore(data, season=2026)
    assert result.skipped is False
    assert result.error is None
    assert aggregator.game_exists(13)

    grichuk = aggregator.conn.execute(
        """
        SELECT home_runs, doubles, stolen_bases, gidp
        FROM batting_logs
        WHERE game_id = 13 AND player_id = 28987
        """
    ).fetchone()
    assert grichuk["home_runs"] == 1

    schlittler = aggregator.conn.execute(
        """
        SELECT ip_outs, decision, loss, game_score
        FROM pitching_logs
        WHERE game_id = 13 AND player_id = 50432
        """
    ).fetchone()
    assert schlittler["ip_outs"] == 7
    assert schlittler["decision"] == "L"
    assert schlittler["loss"] == 1
    assert schlittler["game_score"] == 23


def test_import_skips_duplicate(aggregator: Aggregator) -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    aggregator.import_boxscore(data, season=2026)
    again = aggregator.import_boxscore(data, season=2026)
    assert again.skipped is True


def test_import_all_new(aggregator: Aggregator) -> None:
    result = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    assert result.total_scanned >= 8
    assert result.imported >= 2
    assert result.candidates >= 2

    again = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    assert again.imported == 0
    assert again.skipped_existing == result.total_scanned
    assert again.candidates == 0


def test_import_mlb_only_filter(aggregator: Aggregator, tmp_path: Path) -> None:
    mlb = tmp_path / "game_box_90001.html"
    mlb.write_bytes((SAMPLES_BOX / "game_box_13.html").read_bytes())
    wbc = tmp_path / "game_box_90002.html"
    wbc.write_text(
        "<html><head><title>WBC Box Score, Korea at Japan</title></head></html>",
        encoding="utf-8",
    )

    mlb_only = aggregator.import_all_new(tmp_path, season=2026, mlb_only=True)
    assert mlb_only.imported == 1
    assert mlb_only.skipped_non_mlb == 1

    again = aggregator.import_all_new(tmp_path, season=2026, mlb_only=True)
    assert again.imported == 0
    assert again.skipped_existing == 1
    assert again.skipped_non_mlb == 1


def test_import_mtime_filter(aggregator: Aggregator) -> None:
    import time

    future = time.time() + 3600
    result = aggregator.import_all_new(SAMPLES_BOX, season=2026, since_mtime=future)
    assert result.imported == 0
    assert result.skipped_mtime == result.total_scanned


def test_reimport_boxscore_file(aggregator: Aggregator) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    data = BoxscoreHTMLParser(path).parse()
    first = aggregator.import_boxscore(data, season=2026)
    assert first.skipped is False

    row = aggregator.conn.execute(
        "SELECT home_runs FROM batting_logs WHERE game_id = 13 AND player_id = 28987"
    ).fetchone()
    assert row["home_runs"] == 1

    aggregator.conn.execute(
        """
        UPDATE batting_logs SET home_runs = 99
        WHERE game_id = 13 AND player_id = 28987
        """
    )
    aggregator.conn.commit()

    result = aggregator.reimport_boxscore_file(path, season=2026)
    assert result.error is None
    assert result.skipped is False

    row = aggregator.conn.execute(
        "SELECT home_runs FROM batting_logs WHERE game_id = 13 AND player_id = 28987"
    ).fetchone()
    assert row["home_runs"] == 1


def test_delete_game_import_data(aggregator: Aggregator) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    data = BoxscoreHTMLParser(path).parse()
    aggregator.import_boxscore(data, season=2026)
    assert aggregator.delete_game_import_data(13) is True
    assert not aggregator.game_exists(13)
    assert aggregator.delete_game_import_data(13) is False


def test_summarize_boxscore_file() -> None:
    from core.parser.boxscore_html import summarize_boxscore_file

    summary = summarize_boxscore_file(SAMPLES_BOX / "game_box_13.html")
    assert summary is not None
    assert summary.game_id == 13
    assert summary.is_mlb is True
    assert summary.away_team
    assert summary.home_team
    assert summary.date


def test_season_aggregation(aggregator: Aggregator) -> None:
    for path in (SAMPLES_BOX / "game_box_13.html", SAMPLES_BOX / "game_box_14.html"):
        aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)

    chisholm = aggregator.get_batting_season(1259, 2026)
    assert chisholm is not None
    assert chisholm["ab"] >= 5

    career = aggregator.get_batting_career(1259)
    assert career is not None
    assert career["career_ab"] >= 5

    totals = aggregator.get_season_batting_totals(2026)
    assert len(totals) > 0
