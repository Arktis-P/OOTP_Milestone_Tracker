"""Streak state machine — track runs incrementally, record only when a run ends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.streak.game_log import BattingGameLog, PitchingGameLog
from core.streak.policies import (
    should_record_streak_on_break,
    streak_record_label,
)

StreakOutcome = Literal["skip", "continue", "break"]
EventType = Literal["streak_ended"]


@dataclass
class StreakEvent:
    event_type: EventType
    player_id: int
    team: str
    streak_type: str
    streak_run_id: str
    streak_value: int
    milestone_value: int
    milestone_label: str
    last_success_game_id: int | None
    last_success_game_date: str | None


@dataclass
class StreakState:
    run_index: int = 1
    current: int = 0
    ip_outs_accum: int = 0
    last_success_game_id: int | None = None
    last_success_game_date: str | None = None
    recorded_milestones: set[int] = field(default_factory=set)

    def run_id(self, season: int, player_id: int, streak_type: str) -> str:
        return f"{season}_{player_id}_{streak_type}_{self.run_index:03d}"


def _counter_outcome(success: bool | None) -> StreakOutcome:
    if success is None:
        return "skip"
    return "continue" if success else "break"


def _append_ended_event(
    events: list[StreakEvent],
    *,
    state: StreakState,
    season: int,
    player_id: int,
    team: str,
    streak_type: str,
    ended_value: int,
    policy: dict[str, Any],
    policies_root: dict[str, Any],
) -> None:
    if ended_value <= 0 or not should_record_streak_on_break(ended_value, policy):
        return
    events.append(
        StreakEvent(
            event_type="streak_ended",
            player_id=player_id,
            team=team,
            streak_type=streak_type,
            streak_run_id=state.run_id(season, player_id, streak_type),
            streak_value=0,
            milestone_value=ended_value,
            milestone_label=streak_record_label(
                streak_type, ended_value, policies_root
            ),
            last_success_game_id=state.last_success_game_id,
            last_success_game_date=state.last_success_game_date,
        )
    )


def _reset_streak_state(state: StreakState) -> None:
    state.run_index += 1
    state.current = 0
    state.ip_outs_accum = 0
    state.last_success_game_id = None
    state.last_success_game_date = None
    state.recorded_milestones.clear()


def _eval_batting(streak_type: str, log: BattingGameLog) -> bool | None:
    if not log.batting_opportunity:
        if streak_type in {
            "hit_streak",
            "home_run_streak",
            "rbi_streak",
            "run_streak",
            "stolen_base_streak",
            "walk_streak",
            "on_base_streak",
        }:
            return None

    if streak_type == "hit_streak":
        if log.ab >= 1 and log.h == 0:
            return False
        return log.hit_game

    if streak_type == "home_run_streak":
        return log.hr_game_flag if log.batting_opportunity else None

    if streak_type == "rbi_streak":
        if log.ab >= 1 and not log.rbi_game:
            return False
        return log.rbi_game

    if streak_type == "run_streak":
        return log.run_game

    if streak_type == "stolen_base_streak":
        return log.sb_game_flag

    if streak_type == "walk_streak":
        if log.ab >= 1 and not log.walk_game:
            return False
        return log.walk_game

    if streak_type == "on_base_streak":
        if log.ab >= 1 and not log.on_base_game:
            return False
        return log.on_base_game

    return None


def _eval_pitching(streak_type: str, log: PitchingGameLog) -> bool | None:
    if streak_type == "win_streak":
        if log.decision == "W":
            return True
        if log.decision == "L":
            return False
        return None

    if streak_type == "save_streak":
        if log.decision == "S":
            return True
        if log.decision == "BS":
            return False
        return None

    if streak_type == "qs_streak":
        if not log.is_starter:
            return None
        return log.qs_game

    if streak_type == "scoreless_streak_starter":
        if not log.is_starter:
            return None
        return log.scoreless_appearance

    if streak_type == "scoreless_streak_reliever":
        if log.is_starter:
            return None
        return log.scoreless_appearance

    return None


def update_counter_streak(
    state: StreakState,
    *,
    season: int,
    player_id: int,
    team: str,
    streak_type: str,
    outcome: StreakOutcome,
    policy: dict[str, Any],
    game_id: int,
    game_date: str,
    policies_root: dict[str, Any],
) -> list[StreakEvent]:
    events: list[StreakEvent] = []

    if outcome == "skip":
        return events

    if outcome == "continue":
        state.current += 1
        state.last_success_game_id = game_id
        state.last_success_game_date = game_date
        return events

    ended_value = state.current
    _append_ended_event(
        events,
        state=state,
        season=season,
        player_id=player_id,
        team=team,
        streak_type=streak_type,
        ended_value=ended_value,
        policy=policy,
        policies_root=policies_root,
    )
    _reset_streak_state(state)
    return events


def update_ip_outs_streak(
    state: StreakState,
    *,
    season: int,
    player_id: int,
    team: str,
    streak_type: str,
    log: PitchingGameLog,
    policy: dict[str, Any],
    policies_root: dict[str, Any],
) -> list[StreakEvent]:
    events: list[StreakEvent] = []
    if log.r_allowed > 0:
        ended_value = state.ip_outs_accum
        _append_ended_event(
            events,
            state=state,
            season=season,
            player_id=player_id,
            team=team,
            streak_type=streak_type,
            ended_value=ended_value,
            policy=policy,
            policies_root=policies_root,
        )
        _reset_streak_state(state)
        return events

    state.ip_outs_accum += log.ip_outs
    state.last_success_game_id = log.game_id
    state.last_success_game_date = log.game_date
    return events


def process_batting_log(
    state_map: dict[str, StreakState],
    log: BattingGameLog,
    policies: dict[str, dict[str, Any]],
    policies_root: dict[str, Any],
) -> list[StreakEvent]:
    events: list[StreakEvent] = []
    for streak_type, policy in policies.items():
        state = state_map.setdefault(streak_type, StreakState())
        outcome = _counter_outcome(_eval_batting(streak_type, log))
        events.extend(
            update_counter_streak(
                state,
                season=log.season,
                player_id=log.player_id,
                team=log.team,
                streak_type=streak_type,
                outcome=outcome,
                policy=policy,
                game_id=log.game_id,
                game_date=log.game_date,
                policies_root=policies_root,
            )
        )
    return events


def process_pitching_log(
    state_map: dict[str, StreakState],
    log: PitchingGameLog,
    policies: dict[str, dict[str, Any]],
    policies_root: dict[str, Any],
) -> list[StreakEvent]:
    events: list[StreakEvent] = []
    for streak_type, policy in policies.items():
        state = state_map.setdefault(streak_type, StreakState())
        if streak_type == "scoreless_innings_streak":
            events.extend(
                update_ip_outs_streak(
                    state,
                    season=log.season,
                    player_id=log.player_id,
                    team=log.team,
                    streak_type=streak_type,
                    log=log,
                    policy=policy,
                    policies_root=policies_root,
                )
            )
            continue

        outcome = _counter_outcome(_eval_pitching(streak_type, log))
        events.extend(
            update_counter_streak(
                state,
                season=log.season,
                player_id=log.player_id,
                team=log.team,
                streak_type=streak_type,
                outcome=outcome,
                policy=policy,
                game_id=log.game_id,
                game_date=log.game_date,
                policies_root=policies_root,
            )
        )
    return events
