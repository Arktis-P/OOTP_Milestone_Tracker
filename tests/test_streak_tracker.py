"""Streak tracker unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.stats.aggregator import Aggregator
from core.streak.engine import StreakState, process_pitching_log, update_counter_streak
from core.streak.game_log import BattingGameLog, PitchingGameLog, pitching_log_from_row
from core.streak.policies import (
    format_streak_description,
    load_streak_policies,
    should_record_streak_on_break,
    streak_record_label,
)
from core.streak.tracker import StreakTracker


@pytest.fixture
def policies():
    return load_streak_policies()


def test_should_record_streak_on_break_thresholds(policies) -> None:
    hit = policies["batting"]["hit_streak"]
    assert should_record_streak_on_break(10, hit)
    assert should_record_streak_on_break(23, hit)
    assert not should_record_streak_on_break(9, hit)

    hr = policies["batting"]["home_run_streak"]
    assert should_record_streak_on_break(5, hr)
    assert not should_record_streak_on_break(4, hr)

    innings = policies["pitching"]["scoreless_innings_streak"]
    assert should_record_streak_on_break(90, innings)
    assert not should_record_streak_on_break(89, innings)


def test_streak_record_labels(policies) -> None:
    assert streak_record_label("hit_streak", 12, policies) == "12경기 연속 안타"
    assert streak_record_label(
        "scoreless_innings_streak", 90, policies
    ) == "30.0 연속 무실점 이닝"


def test_format_streak_description(policies) -> None:
    assert format_streak_description(
        start_date="2026-04-05",
        end_date="2026-04-30",
        value=20,
        streak_type="hit_streak",
        policies=policies,
    ) == "2026-04-05 부터 2026-04-30 까지, 20경기 연속"
    assert format_streak_description(
        start_date="2026-04-05",
        end_date="2026-04-30",
        value=90,
        streak_type="scoreless_innings_streak",
        policies=policies,
    ) == "2026-04-05 부터 2026-04-30 까지, 30.0 연속 무실점 이닝"


def test_hit_streak_only_recorded_on_break(policies) -> None:
    state = StreakState()
    hit_policy = policies["batting"]["hit_streak"]
    events = []

    def game(n: int, *, h: int, ab: int = 4) -> BattingGameLog:
        return BattingGameLog(
            season=2026,
            game_id=n,
            game_date=f"2026-03-{n:02d}",
            player_id=42,
            player_name="Test",
            team="Giants",
            ab=ab,
            r=0,
            h=h,
            rbi=0,
            bb=0,
            hit_by_pitch=0,
            home_runs=0,
            stolen_bases=0,
        )

    for n in range(1, 11):
        log = game(n, h=1)
        events.extend(
            update_counter_streak(
                state,
                season=2026,
                player_id=42,
                team="Giants",
                streak_type="hit_streak",
                outcome="continue",
                policy=hit_policy,
                game_id=n,
                game_date=log.game_date,
                policies_root=policies,
            )
        )

    assert events == []
    assert state.current == 10

    log = game(11, h=0, ab=4)
    ended = update_counter_streak(
        state,
        season=2026,
        player_id=42,
        team="Giants",
        streak_type="hit_streak",
        outcome="break",
        policy=hit_policy,
        game_id=11,
        game_date=log.game_date,
        policies_root=policies,
    )
    assert len(ended) == 1
    assert ended[0].event_type == "streak_ended"
    assert ended[0].milestone_value == 10
    assert ended[0].milestone_label == "10경기 연속 안타"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "streak.db")
    yield agg
    agg.close()


def _seed_game_with_hit_streak(aggregator: Aggregator, *, game_id: int, day: int, h: int) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (?, ?, 2026, 'Giants', 'Dodgers', 1, 0, '[]', '[]', 1)
        """,
        (game_id, f"2026-03-{day:02d}"),
    )
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (42, 'Test Player', 'T. Player')
        """,
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date,
            ab, r, h, rbi, bb, k, lob,
            home_runs, stolen_bases, hit_by_pitch, is_substitute, is_grand_slam
        ) VALUES (?, 42, 2026, 'Giants', ?, 4, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """,
        (game_id, f"2026-03-{day:02d}", h),
    )
    aggregator.conn.commit()


def test_tracker_records_milestone_only_when_streak_ends(aggregator: Aggregator) -> None:
    for i in range(1, 11):
        _seed_game_with_hit_streak(aggregator, game_id=i, day=i, h=1)
    _seed_game_with_hit_streak(aggregator, game_id=11, day=11, h=0)

    tracker = StreakTracker(aggregator)
    events = tracker.process_new_games(list(range(1, 12)), 2026)
    hit_events = [e for e in events if e.streak_type == "hit_streak"]
    assert len(hit_events) == 1
    assert hit_events[0].milestone_value == 10

    rows = aggregator.conn.execute(
        """
        SELECT milestone_label, scope, streak_event_type, game_id, milestone_key,
               description, achieved_date
        FROM milestone_records
        WHERE player_id = 42 AND milestone_key = 'streak_hit_streak'
        """
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["scope"] == "streak"
    assert rows[0]["milestone_label"] == "10경기 연속 안타"
    assert rows[0]["streak_event_type"] == "streak_ended"
    assert int(rows[0]["game_id"]) == 11
    assert rows[0]["description"] == "2026-03-01 부터 2026-03-10 까지, 10경기 연속"
    assert rows[0]["achieved_date"] == "2026-03-11"


def _seed_batter_hit_log(
    aggregator: Aggregator,
    *,
    game_id: int,
    day: int,
    player_id: int,
    player_name: str,
    team: str,
    h: int = 1,
) -> None:
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (?, ?, ?)
        """,
        (player_id, player_name, player_name),
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date,
            ab, r, h, rbi, bb, k, lob,
            home_runs, stolen_bases, hit_by_pitch, is_substitute, is_grand_slam
        ) VALUES (?, ?, 2026, ?, ?, 4, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """,
        (game_id, player_id, team, f"2026-03-{day:02d}", h),
    )


def test_tracker_respects_tracked_teams(aggregator: Aggregator) -> None:
    giants = "San Francisco Giants"
    dodgers = "Los Angeles Dodgers"
    for i in range(1, 11):
        _seed_team_game(
            aggregator, game_id=i, day=i, away_team=giants, home_team=dodgers
        )
        _seed_batter_hit_log(
            aggregator,
            game_id=i,
            day=i,
            player_id=42,
            player_name="G. Giant",
            team=giants,
        )
        _seed_batter_hit_log(
            aggregator,
            game_id=i,
            day=i,
            player_id=99,
            player_name="D. Dodger",
            team=dodgers,
        )
    _seed_team_game(aggregator, game_id=11, day=11, away_team=giants, home_team=dodgers)
    _seed_batter_hit_log(
        aggregator, game_id=11, day=11, player_id=42, player_name="G. Giant", team=giants, h=0
    )
    _seed_batter_hit_log(
        aggregator, game_id=11, day=11, player_id=99, player_name="D. Dodger", team=dodgers, h=0
    )
    aggregator.conn.commit()

    tracker = StreakTracker(aggregator, tracked_teams=["SF"])
    tracker.process_new_games(list(range(1, 12)), 2026)

    giants_milestone = aggregator.conn.execute(
        """
        SELECT 1 FROM milestone_records
        WHERE player_id = 42 AND scope = 'streak' AND achieved_value = 10
        """
    ).fetchone()
    dodgers_milestone = aggregator.conn.execute(
        """
        SELECT 1 FROM milestone_records
        WHERE player_id = 99 AND scope = 'streak'
        """
    ).fetchone()
    dodgers_state = aggregator.conn.execute(
        """
        SELECT current_value FROM player_streak_state
        WHERE player_id = 99 AND streak_type = 'hit_streak'
        """
    ).fetchone()

    assert giants_milestone is not None
    assert dodgers_milestone is None
    assert dodgers_state is None


def test_tracker_skips_reprocessing_same_game(aggregator: Aggregator) -> None:
    _seed_game_with_hit_streak(aggregator, game_id=1, day=1, h=1)
    tracker = StreakTracker(aggregator)
    first = tracker.process_new_games([1], 2026)
    second = tracker.process_new_games([1], 2026)
    assert first == []
    assert second == []


def _seed_team_game(
    aggregator: Aggregator,
    *,
    game_id: int,
    day: int,
    away_team: str = "Giants",
    home_team: str = "Dodgers",
) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (?, ?, 2026, ?, ?, 1, 0, '[]', '[]', 1)
        """,
        (game_id, f"2026-03-{day:02d}", away_team, home_team),
    )


def _seed_giants_appearance(
    aggregator: Aggregator, *, game_id: int, day: int, player_id: int = 42
) -> None:
    _seed_team_game(aggregator, game_id=game_id, day=day)
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (?, 'Test Player', 'T. Player')
        """,
        (player_id,),
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date,
            ab, r, h, rbi, bb, k, lob,
            home_runs, stolen_bases, hit_by_pitch, is_substitute, is_grand_slam
        ) VALUES (?, ?, 2026, 'Giants', ?, 4, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """,
        (game_id, player_id, f"2026-03-{day:02d}"),
    )
    aggregator.conn.commit()


def test_appearance_streak_breaks_when_team_plays_without_player(
    aggregator: Aggregator,
) -> None:
    for i in range(1, 6):
        _seed_giants_appearance(aggregator, game_id=i, day=i)

    _seed_team_game(aggregator, game_id=6, day=6)
    aggregator.conn.commit()

    tracker = StreakTracker(aggregator)
    events = tracker.process_new_games(list(range(1, 7)), 2026)

    state = aggregator.conn.execute(
        """
        SELECT current_value FROM player_streak_state
        WHERE player_id = 42 AND streak_type = 'appearance_streak_team_games'
        """
    ).fetchone()
    assert state is not None
    assert int(state["current_value"]) == 0

    ended = [
        e
        for e in events
        if e.streak_type == "appearance_streak_team_games"
        and e.event_type == "streak_ended"
    ]
    assert ended == []


def test_appearance_streak_not_broken_by_other_team_game(aggregator: Aggregator) -> None:
    for i in range(1, 4):
        _seed_giants_appearance(aggregator, game_id=i, day=i)

    _seed_team_game(
        aggregator, game_id=4, day=4, away_team="Yankees", home_team="Dodgers"
    )
    aggregator.conn.commit()

    tracker = StreakTracker(aggregator)
    tracker.process_new_games(list(range(1, 5)), 2026)

    state = aggregator.conn.execute(
        """
        SELECT current_value FROM player_streak_state
        WHERE player_id = 42 AND streak_type = 'appearance_streak_team_games'
        """
    ).fetchone()
    assert state is not None
    assert int(state["current_value"]) == 3


def test_appearance_streak_counts_pitching_only_appearance(aggregator: Aggregator) -> None:
    _seed_team_game(aggregator, game_id=1, day=1)
    aggregator.conn.execute(
        """
        INSERT OR IGNORE INTO players (player_id, full_name, short_name)
        VALUES (99, 'Pitcher Only', 'P. Only')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date,
            ip_outs, h, r, er, bb, k, hr, win, loss, save, is_starter
        ) VALUES (1, 99, 2026, 'Giants', '2026-03-01', 3, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0)
        """
    )
    aggregator.conn.commit()

    tracker = StreakTracker(aggregator)
    tracker.process_new_games([1], 2026)

    row = aggregator.conn.execute(
        """
        SELECT current_value FROM player_streak_state
        WHERE player_id = 99 AND streak_type = 'appearance_streak_team_games'
        """
    ).fetchone()
    assert row is not None
    assert int(row["current_value"]) == 1


def _pitching_log(game_id: int, day: int, *, decision: str = "", player_id: int = 50) -> PitchingGameLog:
    return PitchingGameLog(
        season=2026,
        game_id=game_id,
        game_date=f"2026-03-{day:02d}",
        player_id=player_id,
        player_name="Pitcher",
        team="Giants",
        ip_outs=3,
        r_allowed=0,
        er_allowed=0,
        is_starter=False,
        decision=decision,
    )


def test_win_streak_only_breaks_on_loss(policies) -> None:
    state_map: dict[str, StreakState] = {}
    win_policy = policies["pitching"]["win_streak"]
    pitching_policies = {"win_streak": win_policy}

    for i in range(1, 4):
        process_pitching_log(
            state_map,
            _pitching_log(i, i, decision="W"),
            pitching_policies,
            policies,
        )
    assert state_map["win_streak"].current == 3

    process_pitching_log(
        state_map,
        _pitching_log(4, 4, decision=""),
        pitching_policies,
        policies,
    )
    assert state_map["win_streak"].current == 3

    process_pitching_log(
        state_map,
        _pitching_log(5, 5, decision="L"),
        pitching_policies,
        policies,
    )
    assert state_map["win_streak"].current == 0


def test_save_streak_only_breaks_on_blown_save(policies) -> None:
    state_map: dict[str, StreakState] = {}
    save_policy = policies["pitching"]["save_streak"]
    pitching_policies = {"save_streak": save_policy}

    for i in range(1, 3):
        process_pitching_log(
            state_map,
            _pitching_log(i, i, decision="S"),
            pitching_policies,
            policies,
        )
    assert state_map["save_streak"].current == 2

    process_pitching_log(
        state_map,
        _pitching_log(3, 3, decision="W"),
        pitching_policies,
        policies,
    )
    assert state_map["save_streak"].current == 2

    process_pitching_log(
        state_map,
        _pitching_log(4, 4, decision="BS"),
        pitching_policies,
        policies,
    )
    assert state_map["save_streak"].current == 0


def test_pitching_log_from_row_normalizes_decision() -> None:
    log = pitching_log_from_row(
        {
            "season": 2026,
            "game_id": 1,
            "date": "2026-03-01",
            "player_id": 1,
            "team": "Giants",
            "ip_outs": 3,
            "r": 0,
            "er": 0,
            "is_starter": 0,
            "decision": "BS",
        }
    )
    assert log.decision == "BS"
    assert log.blown_save
