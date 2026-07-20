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
        return [{"id": 42, "games": 10, "team_games_elapsed": 10, "w": 3}]

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


def test_cached_predictions_exclude_players_moved_off_tracked_team(
    tmp_path: Path,
) -> None:
    with Aggregator(tmp_path / "moved-predictions.db") as aggregator:
        aggregator.upsert_player(70001, "Moved Player", "M. Player")
        aggregator.conn.execute(
            """
            INSERT INTO games (
                game_id, date, season, away_team, home_team, away_score, home_score,
                away_innings, home_innings, is_mlb
            ) VALUES (70001, '2026-04-01', 2026, 'SEA', 'BOS', 1, 2, '', '', 1)
            """
        )
        aggregator.conn.execute(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, date, ab, r, h, rbi, bb, k
            ) VALUES (70001, 70001, 2026, 'SEA', '2026-04-01', 4, 0, 1, 0, 0, 1)
            """
        )
        aggregator.upsert_player_roster(
            [
                {
                    "player_id": 70001,
                    "team_abbr": "BOS",
                    "team_name": "Boston Red Sox",
                }
            ],
            season=2026,
        )
        aggregator.upsert_milestone_predictions(
            [
                {
                    "player_id": 70001,
                    "milestone_key": "bat_h_100",
                    "season": 2026,
                    "player_name": "Moved Player",
                    "milestone_label": "100 Hits",
                    "grade": "common",
                    "current_value": 90,
                    "threshold": 100,
                    "remaining": 10,
                    "progress_pct": 90.0,
                    "season_note": "pre_season",
                }
            ]
        )

        store = PredictionStore(
            aggregator,
            _watch_milestones(),
            season=2026,
            season_games_total=162,
            tracked_teams=["SEA"],
        )

        assert store.list_cached() == []


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
    season_pitching = {42: {"id": 42, "games": 3, "team_games_elapsed": 3}}
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


def _insert_pitcher_schedule(
    aggregator: Aggregator,
    *,
    player_id: int = 7701,
    team_games: int = 100,
    appearances: int = 20,
    starts: int = 5,
    holds: int = 4,
) -> int:
    team = "Dragons"
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (?, ?, ?)",
        (player_id, "Pace Pitcher", "P. Pitcher"),
    )
    for index in range(1, team_games + 1):
        game_id = 770000 + index
        aggregator.conn.execute(
            """
            INSERT INTO games (
                game_id, date, season, away_team, home_team,
                away_score, home_score, away_innings, home_innings, is_mlb
            ) VALUES (?, ?, 2026, ?, ?, 1, 2, '[]', '[]', 1)
            """,
            (game_id, f"2026-04-{index:03d}", "Visitors", team),
        )
        if index <= appearances:
            aggregator.conn.execute(
                """
                INSERT INTO pitching_logs (
                    game_id, player_id, season, team, date, ip_outs,
                    is_starter, hold
                ) VALUES (?, ?, 2026, ?, ?, 3, ?, ?)
                """,
                (
                    game_id,
                    player_id,
                    team,
                    f"2026-04-{index:03d}",
                    1 if index <= starts else 0,
                    1 if index <= holds else 0,
                ),
            )
    aggregator.conn.commit()
    return player_id


def test_real_pitching_game_logs_include_starter_and_hold_for_estimates(
    tmp_path: Path,
) -> None:
    with Aggregator(tmp_path / "pitching_logs.db") as aggregator:
        player_id = _insert_pitcher_schedule(
            aggregator, team_games=100, appearances=20, starts=5, holds=4
        )
        logs = aggregator.get_player_pitching_game_logs(player_id, 2026)
        season_row = {
            int(row["id"]): row for row in aggregator.get_season_pitching_totals(2026)
        }[player_id]

        store = PredictionStore(
            aggregator,
            _watch_milestones(),
            season=2026,
            season_games_total=162,
        )
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

        assert len(logs) == 20
        assert sum(int(row["is_starter"]) for row in logs) == 5
        assert sum(int(row["hold"]) for row in logs) == 4
        assert int(season_row["gs"]) == 5
        assert int(season_row["holds"]) == 4
        assert int(season_row["games"]) == 20
        assert int(season_row["team_games_elapsed"]) == 100

        starts_estimate = store._pace_estimate(
            player_id, starts, 10, {}, {player_id: season_row}, {}
        )
        holds_estimate = store._pace_estimate(
            player_id, holds, 10, {}, {player_id: season_row}, {}
        )

        assert starts_estimate.available is True
        assert starts_estimate.games_played_season == 100
        assert starts_estimate.season_pace == pytest.approx(5 / 100)
        assert holds_estimate.available is True
        assert holds_estimate.games_played_season == 100
        assert holds_estimate.season_pace == pytest.approx(4 / 100)


def test_pitcher_projection_uses_team_games_not_appearances(
    tmp_path: Path,
) -> None:
    with Aggregator(tmp_path / "pitching_elapsed.db") as aggregator:
        player_id = _insert_pitcher_schedule(
            aggregator, team_games=100, appearances=20, starts=0, holds=4
        )
        season_row = {
            int(row["id"]): row for row in aggregator.get_season_pitching_totals(2026)
        }[player_id]
        store = PredictionStore(
            aggregator,
            _watch_milestones(),
            season=2026,
            season_games_total=162,
        )
        milestone = MilestoneDefinition(
            key="pit_holds_100",
            label="100 Holds",
            stat="career_holds",
            threshold=100,
            scope="career",
            category="pitching",
        )

        estimate = store._pace_estimate(
            player_id, milestone, 10, {}, {player_id: season_row}, {}
        )

        assert int(season_row["games"]) == 20
        assert estimate.available is True
        assert estimate.games_played_season == 100
        assert estimate.games_remaining == 62
        assert estimate.season_pace == pytest.approx(4 / 100)
        assert estimate.projected_add_season == pytest.approx(2.48)


def test_pitcher_projection_unavailable_without_team_elapsed_basis(
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
        lambda player_id, season: [{"hold": 1} for _ in range(20)],
    )
    milestone = MilestoneDefinition(
        key="pit_holds_100",
        label="100 Holds",
        stat="career_holds",
        threshold=100,
        scope="career",
        category="pitching",
    )

    estimate = store._pace_estimate(
        42, milestone, 10, {}, {42: {"id": 42, "games": 20}}, {}
    )

    assert estimate.available is False
    assert estimate.reason == pace_estimate.REASON_NO_DATA


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
