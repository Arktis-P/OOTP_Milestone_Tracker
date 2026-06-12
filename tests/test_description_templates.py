"""Milestone description template tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone.description_templates import (
    build_template_a,
    build_template_b,
    build_template_c,
    build_template_d,
    fill_description,
)
from core.milestone.definitions import MilestoneDefinition, load_milestones
from core.parser.game_log_html import extract_player_at_bats
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_LOG = ROOT / "samples" / "game_logs_html"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def log_13() -> Path:
    path = SAMPLES_LOG / "log_13.html"
    if not path.is_file():
        pytest.skip("log_13 sample missing")
    return path


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "desc.db")
    yield agg
    agg.close()


def test_template_a_skips_zero_hr_rbi() -> None:
    assert build_template_a({"ab": 6, "h": 5, "home_runs": 0, "rbi": 0}) == "6타수 5안타"
    assert (
        build_template_a({"ab": 4, "h": 3, "home_runs": 1, "rbi": 5})
        == "4타수 3안타 1홈런 5타점"
    )
    assert build_template_a({"ab": 4, "h": 3, "home_runs": 0, "rbi": 5}) == "4타수 3안타 5타점"


def test_template_b_full_and_simplified() -> None:
    row = {
        "ip_outs": 24,
        "h": 5,
        "bb": 3,
        "k": 9,
        "er": 1,
        "decision": "W",
        "is_sho": 0,
        "save": 0,
        "win": 1,
    }
    assert build_template_b(row) == "8.0이닝 5피안타 3볼넷 9탈삼진 1실점 승리"

    sho_row = {**row, "ip_outs": 27, "h": 3, "er": 0, "is_sho": 1}
    assert build_template_b(sho_row) == "9.0이닝 3피안타 3볼넷 9탈삼진 무실점 완봉승"

    save_row = {
        "ip_outs": 4,
        "h": 0,
        "bb": 0,
        "k": 3,
        "er": 0,
        "decision": "S",
        "is_sho": 0,
        "save": 1,
        "win": 0,
    }
    assert build_template_b(save_row) == "1.1이닝 무피안타 무볼넷 3탈삼진 무실점 세이브"

    assert build_template_b({"ip_outs": 22, "k": 12}, simplified=True) == "7.1이닝 12탈삼진"


def test_template_c_and_d(aggregator: Aggregator) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (50, '2026-04-01', 2026, 'Away', 'Home', 1, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.executemany(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (?, ?, ?)",
        [(1, "A One", "A. One"), (2, "B Two", "B. Two")],
    )
    aggregator.conn.executemany(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, is_substitute
        ) VALUES (50, ?, 2026, 'Home', '2026-04-01', 4, 1, 1, 0)
        """,
        [(1,), (2,)],
    )
    aggregator.conn.commit()

    text = build_template_c(
        "team_game_starter_all_hit",
        50,
        "Home",
        aggregator.conn,
    )
    assert text == "선발(A. One-B. Two) 전원 안타"

    score = build_template_d(50, "Home", aggregator.conn)
    assert score == "3-1 승리"


def test_fill_description_situational_returns_none() -> None:
    milestones = load_milestones(MILESTONES_PATH)
    m = milestones.get_by_key("career_hr_500")
    assert m is not None
    assert fill_description(m, {}) is None


def test_extract_player_at_bats(log_13: Path) -> None:
    entries = extract_player_at_bats(log_13, 24383)
    assert entries
    assert any("Casey Schmitt" in e["raw_text"] for e in entries)
    assert entries[0]["label"].endswith(("초", "말"))
