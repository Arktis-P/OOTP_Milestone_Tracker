"""Milestone prediction store tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.milestone import estimate as pace_estimate
from core.milestone.definitions import (
    MilestoneDefinition,
    MilestoneDefinitions,
    load_milestones,
)
from core.milestone.prediction_store import (
    PredictionStore,
    render_season_basis,
    render_season_note,
)
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


def _watch_milestones() -> MilestoneDefinitions:
    return MilestoneDefinitions(
        batting=[
            MilestoneDefinition(
                key="bat_h_100",
                label="100 Hits",
                stat="career_h",
                threshold=100,
                scope="career",
                category="batting",
                track_from=20,
            ),
            MilestoneDefinition(
                key="bat_h_110",
                label="110 Hits",
                stat="career_h",
                threshold=110,
                scope="career",
                category="batting",
                track_from=30,
            ),
        ],
        pitching=[
            MilestoneDefinition(
                key="pit_w_100",
                label="100 Wins",
                stat="career_wins",
                threshold=100,
                scope="career",
                category="pitching",
                track_from=20,
            ),
            MilestoneDefinition(
                key="pit_w_110",
                label="110 Wins",
                stat="career_wins",
                threshold=110,
                scope="career",
                category="pitching",
                track_from=30,
            ),
        ],
    )


class _PredictionSpyAggregator:
    def __init__(self, *, seeded: bool) -> None:
        self.seeded = seeded
        self.batting_log_calls = 0
        self.pitching_log_calls = 0
        self.upserts: list[dict] = []

    def count_milestone_predictions(self, season: int) -> int:
        return 1 if self.seeded else 0

    def clear_milestone_predictions(self, season: int) -> None:
        self.seeded = False

    def upsert_milestone_predictions(self, rows: list[dict]) -> None:
        self.upserts.extend(rows)

    def delete_milestone_predictions(self, season: int, deletes: list[tuple[int, str]]) -> None:
        pass

    def get_milestone_predictions(self, season: int, **kwargs) -> list[dict]:
        return []

    def get_player_ids_for_games(self, game_ids: list[int]) -> set[int]:
        return {42}

    def get_tracked_players(self, tracked_teams=None, custom_teams=None) -> list[dict]:
        return [{"player_id": 42, "full_name": "Cache Tester", "short_name": "Tester"}]

    def get_career_batting_totals(self) -> list[dict]:
        return [{"id": 42, "h": 90}]

    def get_career_pitching_totals(self) -> list[dict]:
        return [{"id": 42, "w": 90}]

    def get_season_batting_totals(self, season: int) -> list[dict]:
        return [{"id": 42, "games_played": 10, "h": 10}]

    def get_season_pitching_totals(self, season: int) -> list[dict]:
        return [{"id": 42, "games": 10, "w": 3}]

    def get_batting_career(self, player_id: int) -> dict:
        return {"career_h": 90}

    def get_pitching_career(self, player_id: int) -> dict:
        return {"career_wins": 90}

    def get_player_batting_game_logs(self, player_id: int, season: int) -> list[dict]:
        self.batting_log_calls += 1
        return [{"h": 1}, {"h": 2}]

    def get_player_pitching_game_logs(self, player_id: int, season: int) -> list[dict]:
        self.pitching_log_calls += 1
        return [{"win": 1}, {"win": 0}]


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "predict.db"
    with Aggregator(db_path) as agg:
        for name in ("game_box_13.html", "game_box_14.html"):
            data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
            agg.import_boxscore(data, season=2026)
        yield agg


@pytest.fixture
def milestones():
    return load_milestones(ROOT / "data" / "milestones.csv")


def test_track_from_filters_distant_career_totals(
    aggregator: Aggregator, milestones
) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    store.reseed()
    keys = {row.milestone_key for row in store.list_cached()}
    assert "bat_career_hr_500" not in keys


def test_reseed_completes_quickly(aggregator: Aggregator, milestones) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    started = time.perf_counter()
    count = store.reseed()
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    assert count >= 0


def test_update_after_import_refreshes_remaining(
    aggregator: Aggregator, milestones
) -> None:
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    store.reseed()
    updated = store.update_after_import([13, 14])
    assert updated >= 0


def test_reseed_loads_game_logs_once_per_player_category(monkeypatch) -> None:
    spy = _PredictionSpyAggregator(seeded=False)
    store = PredictionStore(
        spy,
        _watch_milestones(),
        season=2026,
        season_games_total=162,
    )
    monkeypatch.setattr(PredictionStore, "_achieved_career_keys", lambda self: set())

    assert store.reseed() == 4
    assert spy.batting_log_calls == 1
    assert spy.pitching_log_calls == 1


def test_update_after_import_loads_game_logs_once_per_player_category(monkeypatch) -> None:
    spy = _PredictionSpyAggregator(seeded=True)
    store = PredictionStore(
        spy,
        _watch_milestones(),
        season=2026,
        season_games_total=162,
    )
    monkeypatch.setattr(PredictionStore, "_achieved_career_keys", lambda self: set())

    assert store.update_after_import([101]) == 4
    assert spy.batting_log_calls == 1
    assert spy.pitching_log_calls == 1


def test_pitching_starts_and_holds_use_log_fields_when_season_totals_lack_columns(
    monkeypatch,
) -> None:
    spy = _PredictionSpyAggregator(seeded=True)
    store = PredictionStore(
        spy,
        _watch_milestones(),
        season=2026,
        season_games_total=162,
    )
    monkeypatch.setattr(
        spy,
        "get_player_pitching_game_logs",
        lambda player_id, season: [
            {"is_starter": 1, "hold": 0},
            {"is_starter": 0, "hold": 1},
            {"is_starter": 1, "hold": 1},
        ],
    )
    season_pitching = {42: {"id": 42, "games": 3}}
    starts = MilestoneDefinition(
        key="pit_gs_100",
        label="100 Starts",
        stat="career_gs",
        threshold=100,
        scope="career",
        category="pitching",
    )
    holds = MilestoneDefinition(
        key="pit_holds_100",
        label="100 Holds",
        stat="career_holds",
        threshold=100,
        scope="career",
        category="pitching",
    )

    starts_estimate = store._pace_estimate(
        42, starts, 10, {}, season_pitching, {}
    )
    holds_estimate = store._pace_estimate(
        42, holds, 10, {}, season_pitching, {}
    )

    assert starts_estimate.available is True
    assert starts_estimate.season_pace == pytest.approx(2 / 3)
    assert holds_estimate.available is True
    assert holds_estimate.season_pace == pytest.approx(2 / 3)


def test_cached_predictions_expose_decoded_pace_and_renderable_note(
    aggregator: Aggregator, milestones
) -> None:
    """list_cached() must decode+render both available and unavailable pace notes.

    store.reseed() alone doesn't guarantee cached rows: the sample boxscores'
    career totals are deliberately far from every milestone threshold (see
    test_track_from_filters_distant_career_totals), so the watch list is
    legitimately empty. This test instead seeds deterministic
    milestone_predictions rows directly to exercise the decode/render
    contract for both pace outcomes.
    """
    store = PredictionStore(
        aggregator,
        milestones,
        season=2026,
        season_games_total=162,
    )
    milestone = milestones.get_by_key("bat_career_hits_1500")
    assert milestone is not None

    available_estimate = pace_estimate.estimate_pace(
        current_value=20,
        games_played_season=10,
        season_games_total=162,
        remaining=1480,
        recent_game_values=[2.0] * 10,
    )
    unavailable_estimate = pace_estimate.PaceEstimate(
        available=False, reason=pace_estimate.REASON_NO_DATA, remaining=1480
    )
    aggregator.upsert_milestone_predictions(
        [
            {
                "player_id": 1,
                "milestone_key": milestone.key,
                "season": 2026,
                "player_name": "Player With Pace",
                "milestone_label": milestone.label,
                "grade": milestone.grade,
                "current_value": 20,
                "threshold": milestone.threshold,
                "remaining": 1480,
                "progress_pct": 1.3,
                "season_note": pace_estimate.encode_pace_estimate(available_estimate),
            },
            {
                "player_id": 2,
                "milestone_key": milestone.key,
                "season": 2026,
                "player_name": "Player Without Data",
                "milestone_label": milestone.label,
                "grade": milestone.grade,
                "current_value": 0,
                "threshold": milestone.threshold,
                "remaining": 1480,
                "progress_pct": 0.0,
                "season_note": pace_estimate.encode_pace_estimate(unavailable_estimate),
            },
        ]
    )

    items = store.list_cached()
    assert len(items) == 2
    for item in items:
        assert render_season_note(item.season_note) != ""
        assert render_season_basis(item.season_note) != ""
        assert item.pace is not None
        assert item.pace.available in (True, False)
        if item.pace.available:
            assert item.pace.games_played_season > 0
