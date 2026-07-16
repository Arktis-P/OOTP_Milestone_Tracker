"""Tests for the explainable milestone pace/estimate module."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestone import estimate as pace_estimate
from core.milestone.definitions import load_milestones
from core.milestone.prediction_store import (
    PredictionStore,
    render_season_basis,
    render_season_note,
)
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


# ── Pure estimate_pace() unit tests ─────────────────────────────────────────


def test_empty_no_games_is_unavailable() -> None:
    result = pace_estimate.estimate_pace(
        current_value=0,
        games_played_season=0,
        season_games_total=162,
        remaining=50,
        recent_game_values=[],
    )
    assert result.available is False
    assert result.reason == pace_estimate.REASON_NO_DATA
    assert result.season_pace is None
    assert result.games_to_target is None


def test_fewer_than_thirty_games_uses_full_sample() -> None:
    recent = [1.0] * 12
    result = pace_estimate.estimate_pace(
        current_value=12,
        games_played_season=20,
        season_games_total=162,
        remaining=50,
        recent_game_values=recent,
    )
    assert result.available is True
    assert result.recent_games == 12
    assert result.recent_pace == pytest.approx(1.0)


def test_exactly_thirty_games_uses_all_of_them() -> None:
    recent = [2.0] * 30
    result = pace_estimate.estimate_pace(
        current_value=40,
        games_played_season=30,
        season_games_total=162,
        remaining=100,
        recent_game_values=recent,
    )
    assert result.recent_games == 30
    assert result.recent_pace == pytest.approx(2.0)


def test_more_than_thirty_games_truncates_to_most_recent_thirty() -> None:
    # 20 old games with a low rate, then 30 recent games with a high rate.
    old = [0.0] * 20
    recent = [3.0] * 30
    result = pace_estimate.estimate_pace(
        current_value=sum(old) + sum(recent),
        games_played_season=50,
        season_games_total=162,
        remaining=200,
        recent_game_values=old + recent,
    )
    assert result.recent_games == 30
    assert result.recent_pace == pytest.approx(3.0)
    # Season-full pace is diluted by the old, lower-rate games.
    assert result.season_pace == pytest.approx(90 / 50)
    assert result.season_pace < result.recent_pace


def test_zero_rate_is_available_but_not_on_pace() -> None:
    result = pace_estimate.estimate_pace(
        current_value=0,
        games_played_season=25,
        season_games_total=162,
        remaining=30,
        recent_game_values=[0.0] * 25,
    )
    assert result.available is True
    assert result.season_pace == 0.0
    assert result.projected_add_season == 0.0
    assert result.possible_season is False
    assert result.games_to_target is None  # can't estimate at a zero rate


def test_unsupported_lower_direction_is_unavailable() -> None:
    result = pace_estimate.estimate_pace(
        current_value=3.5,
        games_played_season=20,
        season_games_total=162,
        remaining=1.0,
        recent_game_values=[3.0] * 10,
        direction="lower",
    )
    assert result.available is False
    assert result.reason == pace_estimate.REASON_UNSUPPORTED


def test_unsupported_ratio_stat_is_unavailable() -> None:
    result = pace_estimate.estimate_pace(
        current_value=0.310,
        games_played_season=20,
        season_games_total=162,
        remaining=0.02,
        recent_game_values=[0.3] * 10,
        is_ratio=True,
    )
    assert result.available is False
    assert result.reason == pace_estimate.REASON_UNSUPPORTED


def test_is_stat_supported_rejects_lower_and_ratio() -> None:
    assert pace_estimate.is_stat_supported("career_era", "lower", "pitching") is False
    assert pace_estimate.is_stat_supported("season_avg", "higher", "batting") is False
    assert pace_estimate.is_stat_supported("career_hr", "higher", "batting") is True
    assert pace_estimate.is_stat_supported("career_gs", "higher", "pitching") is True
    assert pace_estimate.is_stat_supported("career_holds", "higher", "pitching") is True


def test_pitching_recent_values_support_starts_and_holds() -> None:
    logs = [
        {"is_starter": 1, "hold": 0},
        {"is_starter": 0, "hold": 1},
        {"is_starter": 1, "hold": 1},
    ]
    assert pace_estimate.pitching_recent_values("career_gs", logs) == [1.0, 0.0, 1.0]
    assert pace_estimate.pitching_recent_values("career_holds", logs) == [0.0, 1.0, 1.0]


def test_games_to_target_uses_season_pace() -> None:
    result = pace_estimate.estimate_pace(
        current_value=10,
        games_played_season=20,
        season_games_total=162,
        remaining=100,
        recent_game_values=[0.5] * 20,
    )
    assert result.season_pace == pytest.approx(0.5)
    assert result.games_to_target == pytest.approx(200.0)


# ── Encode/decode round-trip ────────────────────────────────────────────────


def test_encode_decode_round_trip_available() -> None:
    estimate = pace_estimate.estimate_pace(
        current_value=15,
        games_played_season=30,
        season_games_total=162,
        remaining=40,
        recent_game_values=[0.5] * 30,
    )
    encoded = pace_estimate.encode_pace_estimate(estimate)
    decoded = pace_estimate.decode_pace_estimate(encoded)
    assert decoded is not None
    assert decoded.available is True
    assert decoded.games_played_season == 30
    assert decoded.recent_games == 30
    assert decoded.possible_season == estimate.possible_season


def test_encode_decode_round_trip_unavailable() -> None:
    estimate = pace_estimate.PaceEstimate(
        available=False, reason=pace_estimate.REASON_NO_DATA, remaining=50
    )
    encoded = pace_estimate.encode_pace_estimate(estimate)
    decoded = pace_estimate.decode_pace_estimate(encoded)
    assert decoded is not None
    assert decoded.available is False
    assert decoded.reason == pace_estimate.REASON_NO_DATA


def test_decode_handles_legacy_and_garbage_text() -> None:
    assert pace_estimate.decode_pace_estimate("") is None
    assert pace_estimate.decode_pace_estimate("pre_season") is None
    assert pace_estimate.decode_pace_estimate("achievable|12") is None
    assert pace_estimate.decode_pace_estimate("not_achievable|12|8") is None


def test_render_season_note_falls_back_for_legacy_text() -> None:
    # render_season_note must not crash on pre-existing legacy-encoded rows.
    assert render_season_note("pre_season")
    assert "12" in render_season_note("achievable|12")
    assert render_season_basis("pre_season")  # explains itself, doesn't crash


def test_render_strings_do_not_expose_replacement_markers() -> None:
    text = pace_estimate.render_pace_summary(
        pace_estimate.PaceEstimate(
            available=False,
            reason=pace_estimate.REASON_UNSUPPORTED,
        )
    )
    assert chr(0xFFFD) not in text
    assert "?" * 2 not in text


# ── Integration: career vs season handling through PredictionStore ─────────


@pytest.fixture
def milestones():
    return load_milestones(ROOT / "data" / "milestones.csv")


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "estimate.db"
    with Aggregator(db_path) as agg:
        for name in ("game_box_13.html", "game_box_14.html"):
            data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
            agg.import_boxscore(data, season=2026)
        yield agg


def test_prediction_store_pace_estimate_uses_season_games_not_career(
    aggregator: Aggregator, milestones
) -> None:
    """Career milestones must pace off *this season's* games, not career totals."""
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    season_rows = aggregator.get_season_batting_totals(2026)
    assert season_rows, "fixture boxscores should produce season batting totals"
    row = season_rows[0]
    player_id = int(row["id"])
    season_games_played = int(row["games_played"])
    assert 0 < season_games_played <= 2  # only 2 boxscores imported in this fixture

    milestone = milestones.get_by_key("bat_career_hits_1500")
    assert milestone is not None

    # A career remaining far larger than what 2 games could ever close this season.
    estimate = store._pace_estimate(
        player_id, milestone, remaining=1490, season_batting={player_id: row}, season_pitching={}
    )
    assert estimate.available is True
    assert estimate.games_played_season == season_games_played
    assert estimate.recent_games == season_games_played
    assert estimate.recent_games <= pace_estimate.RECENT_GAMES_WINDOW
    assert estimate.possible_season is False  # can't close 1490 hits in a couple games

    encoded = pace_estimate.encode_pace_estimate(estimate)
    assert isinstance(render_season_note(encoded), str)
    assert isinstance(render_season_basis(encoded), str)


def test_prediction_store_pace_estimate_unavailable_without_season_data(
    aggregator: Aggregator, milestones
) -> None:
    milestone = milestones.get_by_key("bat_career_hits_1500")
    assert milestone is not None
    store = PredictionStore(aggregator, milestones, season=2026, season_games_total=162)

    estimate = store._pace_estimate(
        999999, milestone, remaining=100, season_batting={}, season_pitching={}
    )
    assert estimate.available is False
    assert estimate.reason == pace_estimate.REASON_NO_DATA


def test_prediction_store_pace_estimate_unsupported_for_lower_direction(
    aggregator: Aggregator, milestones
) -> None:
    era_milestone = milestones.get_by_key("pit_season_era_2")
    assert era_milestone is not None
    assert era_milestone.direction == "lower"
    store = PredictionStore(aggregator, milestones, season=2026, season_games_total=162)

    estimate = store._pace_estimate(
        1, era_milestone, remaining=1.0, season_batting={}, season_pitching={1: {"games": 10}}
    )
    assert estimate.available is False
    assert estimate.reason == pace_estimate.REASON_UNSUPPORTED
