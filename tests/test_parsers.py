"""Parser unit tests against local OOTP samples."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.parser.boxscore_html import BoxscoreHTMLParser, ParserError, peek_is_mlb_boxscore
from core.parser.game_log_html import GameLogHTMLParser

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_LOG = ROOT / "samples" / "game_logs_html"


@pytest.fixture
def box_13() -> Path:
    return SAMPLES_BOX / "game_box_13.html"


@pytest.fixture
def box_14() -> Path:
    return SAMPLES_BOX / "game_box_14.html"


@pytest.fixture
def log_13() -> Path:
    return SAMPLES_LOG / "log_13.html"


@pytest.fixture
def log_14() -> Path:
    return SAMPLES_LOG / "log_14.html"


def test_peek_is_mlb_boxscore(box_13: Path, tmp_path: Path) -> None:
    assert peek_is_mlb_boxscore(box_13) is True
    non_mlb = tmp_path / "game_box_99999.html"
    non_mlb.write_text(
        "<html><head><title>WBC Box Score, Korea at Japan</title></head></html>",
        encoding="utf-8",
    )
    assert peek_is_mlb_boxscore(non_mlb) is False


def test_boxscore_meta(box_13: Path) -> None:
    data = BoxscoreHTMLParser(box_13).parse()
    assert data.meta.game_id == 13
    assert data.meta.away_team == "New York Yankees"
    assert data.meta.home_team == "San Francisco Giants"
    assert data.meta.away_score == 4
    assert data.meta.home_score == 9
    assert data.meta.date == "2026-03-27"
    assert data.meta.away_record == "0-2"
    assert data.meta.home_record == "2-0"
    assert data.meta.away_innings == [0, 0, 0, 0, 0, 2, 0, 1, 1]
    assert data.meta.home_innings == [1, 3, 4, 1, 0, 0, 0, 0, 0]
    assert data.meta.away_hits == 12
    assert data.meta.home_hits == 13
    assert data.meta.ballpark == "Oracle Park"
    assert data.meta.attendance == 35909
    assert data.meta.game_time == "3:36"


def test_boxscore_batting(box_13: Path) -> None:
    data = BoxscoreHTMLParser(box_13).parse()
    chisholm = data.away_batting[0]
    assert chisholm.player_id == 1259
    assert chisholm.player_name == "J. Chisholm Jr."
    assert chisholm.ab == 5
    assert chisholm.h == 1
    assert chisholm.is_substitute is False

    grichuk = data.away_batting[4]
    assert grichuk.is_substitute is True
    assert grichuk.sub_label == "a"
    assert grichuk.player_id == 28987
    assert grichuk.season_hr == 1


def test_boxscore_pitching(box_13: Path) -> None:
    data = BoxscoreHTMLParser(box_13).parse()
    schlittler = data.away_pitching[0]
    assert schlittler.player_id == 50432
    assert schlittler.decision == "L"
    assert schlittler.decision_record == "(0-1)"
    assert schlittler.ip == pytest.approx(2.333, abs=0.01)
    assert schlittler.era == pytest.approx(19.29, abs=0.01)


def test_boxscore_game_notes(box_13: Path) -> None:
    data = BoxscoreHTMLParser(box_13).parse()
    assert data.game_notes.player_of_game == "Jung-hoo Lee"
    assert data.game_notes.player_of_game_id == 41755
    assert "injured" in data.game_notes.special_notes.lower()


def test_boxscore_parses_second_file(box_14: Path) -> None:
    data = BoxscoreHTMLParser(box_14).parse()
    assert data.meta.game_id == 14
    assert data.meta.away_team == "Athletics"
    assert data.meta.home_team == "Toronto Blue Jays"
    assert len(data.away_batting) > 0
    assert len(data.home_pitching) > 0


def test_game_log_structure(log_13: Path) -> None:
    data = GameLogHTMLParser(log_13).parse()
    assert data.game_id == 13
    assert data.away_team == "New York Yankees"
    assert data.home_team == "San Francisco Giants"
    assert data.date == "2026-03-27"
    assert len(data.innings) > 0

    first_ab = data.innings[0].at_bats[0]
    assert first_ab.batter_name == "Jazz Chisholm Jr."
    assert first_ab.batter_id == 1259
    assert first_ab.result == "Strikeout"
    assert first_ab.half == "TOP"
    assert first_ab.inning == 1


def test_game_log_home_run(log_13: Path) -> None:
    data = GameLogHTMLParser(log_13).parse()
    bottom_2nd = data.innings[3]
    assert bottom_2nd.half == "BOTTOM"
    assert bottom_2nd.inning_num == 2

    schmitt_ab = bottom_2nd.at_bats[1]
    assert schmitt_ab.batter_name == "Casey Schmitt"
    assert schmitt_ab.batter_id == 24383
    assert schmitt_ab.result == "Home Run"
    assert schmitt_ab.distance == 397


def test_game_log_parses_second_file(log_14: Path) -> None:
    data = GameLogHTMLParser(log_14).parse()
    assert data.game_id == 14
    assert len(data.innings) > 0
    assert data.innings[0].at_bats


def test_parser_error_missing_file() -> None:
    with pytest.raises(ParserError):
        BoxscoreHTMLParser("samples/boxscore_html/does_not_exist.html").parse()
