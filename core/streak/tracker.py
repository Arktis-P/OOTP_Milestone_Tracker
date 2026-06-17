"""Incremental streak tracking backed by SQLite state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
from core.streak.engine import (
    StreakEvent,
    StreakState,
    process_batting_log,
    process_pitching_log,
    update_counter_streak,
)

from core.streak.game_log import batting_log_from_row, pitching_log_from_row
from core.streak.memory_store import InMemoryStreakStore
from core.streak.policies import (
    batting_policies,
    load_streak_policies,
    pitching_policies,
)

APPEARANCE_STREAK_TYPE = "appearance_streak_team_games"
_LEGACY_APPEARANCE_STREAK_TYPE = "appearance_streak_player_games"

ProgressCallback = Callable[[int, int, str], None]


class StreakTracker:
    """Process newly imported games and record streak milestones incrementally."""

    def __init__(
        self,
        aggregator: Aggregator,
        *,
        policies_path: str | Path | None = None,
        tracked_teams: list[str] | None = None,
        custom_teams: dict[str, str] | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.tracked_teams = tracked_teams or []
        self.custom_teams = custom_teams or {}
        self.policies = load_streak_policies(policies_path)
        self.labels: dict[str, str] = dict(self.policies.get("labels") or {})
        self._batting_policies = batting_policies(self.policies)
        self._pitching_policies = pitching_policies(self.policies)
        self._appearance_policy = self._batting_policies.get(APPEARANCE_STREAK_TYPE)
        self._batting_streak_policies = {
            key: value
            for key, value in self._batting_policies.items()
            if key != APPEARANCE_STREAK_TYPE
        }
        self._replay_store: InMemoryStreakStore | None = None

    def replay_season(self, season: int) -> InMemoryStreakStore:
        """Replay all season games in memory (no DB writes). Used for CSV export."""
        self._replay_store = InMemoryStreakStore()
        rows = self.aggregator.conn.execute(
            "SELECT game_id FROM games WHERE season = ? ORDER BY date, game_id",
            (season,),
        ).fetchall()
        for row in rows:
            self._process_single_game(int(row["game_id"]), season, replay=True)
        store = self._replay_store
        self._replay_store = None
        return store

    def replay_season_with_snapshots(
        self, season: int
    ) -> tuple[InMemoryStreakStore, list[dict[str, Any]], list[dict[str, Any]]]:
        """Replay season and collect per-game batting/pitching streak snapshots."""
        self._replay_store = InMemoryStreakStore()
        batting_types = set(self._batting_policies.keys())
        pitching_types = set(self._pitching_policies.keys())
        bat_snapshots: list[dict[str, Any]] = []
        pit_snapshots: list[dict[str, Any]] = []

        rows = self.aggregator.conn.execute(
            "SELECT game_id, date FROM games WHERE season = ? ORDER BY date, game_id",
            (season,),
        ).fetchall()
        for row in rows:
            game_id = int(row["game_id"])
            game_date = str(row["date"])
            self._process_single_game(game_id, season, replay=True)
            bat_rows, pit_rows = self._collect_snapshots(
                season,
                game_id,
                game_date,
                batting_types,
                pitching_types,
            )
            bat_snapshots.extend(bat_rows)
            pit_snapshots.extend(pit_rows)

        store = self._replay_store
        self._replay_store = None
        return store, bat_snapshots, pit_snapshots

    def _collect_snapshots(
        self,
        season: int,
        game_id: int,
        game_date: str,
        batting_types: set[str],
        pitching_types: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self._replay_store:
            return [], []

        batting_rows: list[dict[str, Any]] = []
        pitching_rows: list[dict[str, Any]] = []
        for (player_id, streak_type), state in self._replay_store.states.items():
            if state.current <= 0 and state.ip_outs_accum <= 0:
                continue
            team, player_name = self._player_identity_in_game(game_id, player_id)
            base = {
                "season": season,
                "game_id": game_id,
                "game_date": game_date,
                "player_id": player_id,
                "player_name": player_name,
                "team": team,
                "streak_type": streak_type,
                "streak_label": self.labels.get(streak_type, streak_type),
                "current_value": state.current,
                "ip_outs_accum": state.ip_outs_accum,
                "run_index": state.run_index,
                "streak_run_id": state.run_id(season, player_id, streak_type),
            }
            if streak_type in batting_types:
                batting_rows.append(base)
            elif streak_type in pitching_types:
                pitching_rows.append(base)
        return batting_rows, pitching_rows

    def _player_identity_in_game(
        self, game_id: int, player_id: int
    ) -> tuple[str, str]:
        row = self.aggregator.conn.execute(
            """
            SELECT bl.team, COALESCE(p.short_name, p.full_name, '') AS player_name
            FROM batting_logs bl
            LEFT JOIN players p ON p.player_id = bl.player_id
            WHERE bl.game_id = ? AND bl.player_id = ?
            UNION ALL
            SELECT pl.team, COALESCE(p.short_name, p.full_name, '') AS player_name
            FROM pitching_logs pl
            LEFT JOIN players p ON p.player_id = pl.player_id
            WHERE pl.game_id = ? AND pl.player_id = ?
            LIMIT 1
            """,
            (game_id, player_id, game_id, player_id),
        ).fetchone()
        if row:
            return str(row["team"]), str(row["player_name"])
        row = self.aggregator.conn.execute(
            """
            SELECT COALESCE(p.short_name, p.full_name, '') AS player_name
            FROM players p WHERE p.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        name = str(row["player_name"]) if row else ""
        return "", name

    def process_new_games(
        self,
        game_ids: list[int],
        season: int,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> list[StreakEvent]:
        if not game_ids:
            return []

        ordered = self._sort_game_ids(game_ids)
        all_events: list[StreakEvent] = []
        total = len(ordered)
        for index, game_id in enumerate(ordered, start=1):
            if progress_callback:
                progress_callback(index, total, f"streak game {game_id}")
            all_events.extend(self._process_single_game(game_id, season))
        return all_events

    def _sort_game_ids(self, game_ids: list[int]) -> list[int]:
        if not game_ids:
            return []
        placeholders = ",".join("?" * len(game_ids))
        rows = self.aggregator.conn.execute(
            f"""
            SELECT game_id FROM games
            WHERE game_id IN ({placeholders})
            ORDER BY date, game_id
            """,
            game_ids,
        ).fetchall()
        return [int(row["game_id"]) for row in rows]

    def _process_single_game(
        self, game_id: int, season: int, *, replay: bool = False
    ) -> list[StreakEvent]:
        if not replay and self._game_already_processed(game_id, season):
            return []

        events: list[StreakEvent] = []
        batting_rows = self._filter_game_log_rows(self._fetch_batting_rows(game_id))
        pitching_rows = self._filter_game_log_rows(self._fetch_pitching_rows(game_id))
        game_meta = self._fetch_game_meta(game_id)

        for row in batting_rows:
            log = batting_log_from_row(row, player_name=str(row.get("player_name") or ""))
            state_map = self._load_player_states(
                season, log.player_id, self._batting_streak_policies
            )
            batch = process_batting_log(
                state_map, log, self._batting_streak_policies, self.policies
            )
            self._save_player_states(season, log.player_id, state_map)
            events.extend(batch)

        for row in pitching_rows:
            log = pitching_log_from_row(row, player_name=str(row.get("player_name") or ""))
            state_map = self._load_player_states(season, log.player_id, self._pitching_policies)
            batch = process_pitching_log(
                state_map, log, self._pitching_policies, self.policies
            )
            self._save_player_states(season, log.player_id, state_map)
            events.extend(batch)

        if self._appearance_policy and game_meta:
            events.extend(
                self._process_appearance_streaks(
                    game_id,
                    season,
                    game_meta,
                    batting_rows,
                    pitching_rows,
                )
            )

        for event in events:
            if not replay:
                self._persist_event(event, season, game_id)

        if not replay:
            self._mark_game_processed(game_id, season)
            if events:
                self.aggregator.conn.commit()
        return events

    def _fetch_game_meta(self, game_id: int) -> dict[str, Any] | None:
        row = self.aggregator.conn.execute(
            """
            SELECT game_id, date, away_team, home_team, away_team_id, home_team_id
            FROM games
            WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
        return dict(row) if row else None

    def _process_appearance_streaks(
        self,
        game_id: int,
        season: int,
        game_meta: dict[str, Any],
        batting_rows: list[dict[str, Any]],
        pitching_rows: list[dict[str, Any]],
    ) -> list[StreakEvent]:
        policy = self._appearance_policy
        if not policy:
            return []

        game_date = str(game_meta["date"])
        away_team = str(game_meta["away_team"])
        home_team = str(game_meta["home_team"])
        playing_teams = {away_team, home_team}
        playing_team_ids = {
            int(value)
            for value in (game_meta.get("away_team_id"), game_meta.get("home_team_id"))
            if value
        }

        appeared_by_id: set[tuple[int, int]] = set()
        appeared_by_name: set[tuple[int, str]] = set()
        for row in batting_rows + pitching_rows:
            player_id = int(row["player_id"])
            team = str(row["team"])
            appeared_by_name.add((player_id, team))
            team_id = row.get("team_id")
            if team_id:
                appeared_by_id.add((player_id, int(team_id)))

        events: list[StreakEvent] = []
        handled_players: set[int] = set()

        for player_id, team in sorted(appeared_by_name):
            if player_id in handled_players:
                continue
            if not self._team_is_tracked(team):
                continue
            handled_players.add(player_id)
            state_map = self._load_appearance_state(season, player_id)
            state = state_map[APPEARANCE_STREAK_TYPE]
            batch = update_counter_streak(
                state,
                season=season,
                player_id=player_id,
                team=team,
                streak_type=APPEARANCE_STREAK_TYPE,
                outcome="continue",
                policy=policy,
                game_id=game_id,
                game_date=game_date,
                policies_root=self.policies,
            )
            self._save_appearance_state(season, player_id, state)
            events.extend(batch)

        active_rows = self._active_appearance_streak_players(season)

        for row in active_rows:
            player_id = int(row["player_id"])
            if player_id in handled_players:
                continue

            effective_team, effective_team_id = self._player_team_before_game(
                season, player_id, game_id, game_date
            )
            if not self._team_is_tracked(effective_team):
                continue
            if not self._team_is_playing_today(
                effective_team,
                effective_team_id,
                playing_teams,
                playing_team_ids,
            ):
                continue
            if self._player_appeared_today(
                player_id,
                effective_team,
                effective_team_id,
                appeared_by_name,
                appeared_by_id,
            ):
                continue

            state_map = self._load_appearance_state(season, player_id)
            state = state_map[APPEARANCE_STREAK_TYPE]
            batch = update_counter_streak(
                state,
                season=season,
                player_id=player_id,
                team=effective_team or "",
                streak_type=APPEARANCE_STREAK_TYPE,
                outcome="break",
                policy=policy,
                game_id=game_id,
                game_date=game_date,
                policies_root=self.policies,
            )
            self._save_appearance_state(season, player_id, state)
            events.extend(batch)

        return events

    @staticmethod
    def _team_is_playing_today(
        team_name: str | None,
        team_id: int | None,
        playing_names: set[str],
        playing_ids: set[int],
    ) -> bool:
        if team_id and playing_ids:
            return team_id in playing_ids
        return bool(team_name and team_name in playing_names)

    @staticmethod
    def _player_appeared_today(
        player_id: int,
        team_name: str | None,
        team_id: int | None,
        appeared_by_name: set[tuple[int, str]],
        appeared_by_id: set[tuple[int, int]],
    ) -> bool:
        if team_id and (player_id, team_id) in appeared_by_id:
            return True
        return bool(team_name and (player_id, team_name) in appeared_by_name)

    def _active_appearance_streak_players(self, season: int) -> list[Any]:
        if self._replay_store:
            return [
                {"player_id": player_id}
                for player_id in self._replay_store.active_players(
                    APPEARANCE_STREAK_TYPE
                )
            ]
        return self.aggregator.conn.execute(
            """
            SELECT player_id, current_value
            FROM player_streak_state
            WHERE season = ? AND streak_type = ? AND current_value > 0
            """,
            (season, APPEARANCE_STREAK_TYPE),
        ).fetchall()

    def _player_team_before_game(
        self,
        season: int,
        player_id: int,
        game_id: int,
        game_date: str,
    ) -> tuple[str | None, int | None]:
        row = self.aggregator.conn.execute(
            """
            SELECT team, team_id FROM (
                SELECT bl.team, bl.team_id, g.date, bl.game_id
                FROM batting_logs bl
                JOIN games g ON g.game_id = bl.game_id
                WHERE bl.player_id = ? AND bl.season = ?
                UNION ALL
                SELECT pl.team, pl.team_id, g.date, pl.game_id
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id
                WHERE pl.player_id = ? AND pl.season = ?
            )
            WHERE date < ? OR (date = ? AND game_id < ?)
            ORDER BY date DESC, game_id DESC
            LIMIT 1
            """,
            (player_id, season, player_id, season, game_date, game_date, game_id),
        ).fetchone()
        if not row:
            return None, None
        team = str(row["team"]) if row["team"] else None
        team_id = int(row["team_id"]) if row["team_id"] else None
        if team_id is None and team:
            from core.teams.registry import TeamRegistry

            team_id = TeamRegistry(self.aggregator.conn).resolve_id(team)
        return team, team_id

    def _load_appearance_state(
        self, season: int, player_id: int
    ) -> dict[str, StreakState]:
        return self._load_player_states(
            season,
            player_id,
            {APPEARANCE_STREAK_TYPE: self._appearance_policy or {}},
        )

    def _save_appearance_state(
        self, season: int, player_id: int, state: StreakState
    ) -> None:
        self._save_player_states(
            season,
            player_id,
            {APPEARANCE_STREAK_TYPE: state},
        )

    def _game_already_processed(self, game_id: int, season: int) -> bool:
        row = self.aggregator.conn.execute(
            """
            SELECT 1 FROM streak_processed_games
            WHERE season = ? AND game_id = ?
            """,
            (season, game_id),
        ).fetchone()
        return row is not None

    def _mark_game_processed(self, game_id: int, season: int) -> None:
        self.aggregator.conn.execute(
            """
            INSERT OR IGNORE INTO streak_processed_games (season, game_id)
            VALUES (?, ?)
            """,
            (season, game_id),
        )

    def _fetch_batting_rows(self, game_id: int) -> list[dict[str, Any]]:
        rows = self.aggregator.conn.execute(
            """
            SELECT bl.*, COALESCE(p.short_name, p.full_name, '') AS player_name
            FROM batting_logs bl
            LEFT JOIN players p ON p.player_id = bl.player_id
            WHERE bl.game_id = ?
            ORDER BY bl.id
            """,
            (game_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _fetch_pitching_rows(self, game_id: int) -> list[dict[str, Any]]:
        rows = self.aggregator.conn.execute(
            """
            SELECT pl.*,
                   COALESCE(pl.is_starter, 0) AS is_starter,
                   COALESCE(p.short_name, p.full_name, '') AS player_name
            FROM pitching_logs pl
            LEFT JOIN players p ON p.player_id = pl.player_id
            WHERE pl.game_id = ?
            ORDER BY pl.id
            """,
            (game_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if not int(item.get("is_starter") or 0):
                item["is_starter"] = self._infer_is_starter(
                    game_id, str(item["team"]), int(item["id"])
                )
            result.append(item)
        return result

    def _infer_is_starter(self, game_id: int, team: str, log_id: int) -> int:
        row = self.aggregator.conn.execute(
            """
            SELECT MIN(id) AS starter_id
            FROM pitching_logs
            WHERE game_id = ? AND team = ?
            """,
            (game_id, team),
        ).fetchone()
        if row and row["starter_id"] == log_id:
            return 1
        return 0

    def _load_player_states(
        self,
        season: int,
        player_id: int,
        policies: dict[str, dict[str, Any]],
    ) -> dict[str, StreakState]:
        if self._replay_store:
            return self._replay_store.load_player_states(player_id, policies)

        state_map: dict[str, StreakState] = {}
        for streak_type in policies:
            row = self._fetch_streak_state_row(season, player_id, streak_type)
            if streak_type == APPEARANCE_STREAK_TYPE and not row:
                row = self._fetch_streak_state_row(
                    season, player_id, _LEGACY_APPEARANCE_STREAK_TYPE
                )
                if row:
                    self._migrate_legacy_appearance_state(season, player_id, row)
            if not row:
                state_map[streak_type] = StreakState()
                continue
            recorded_raw = str(row["recorded_milestones"] or "")
            recorded = {
                int(part)
                for part in recorded_raw.split(",")
                if part.strip().isdigit()
            }
            state_map[streak_type] = StreakState(
                run_index=int(row["run_index"]),
                current=int(row["current_value"]),
                ip_outs_accum=int(row["ip_outs_accum"]),
                last_success_game_id=row["last_success_game_id"],
                last_success_game_date=row["last_success_game_date"],
                recorded_milestones=recorded,
            )
        return state_map

    def _fetch_streak_state_row(
        self, season: int, player_id: int, streak_type: str
    ) -> sqlite3.Row | None:
        return self.aggregator.conn.execute(
            """
            SELECT run_index, current_value, ip_outs_accum,
                   last_success_game_id, last_success_game_date,
                   recorded_milestones
            FROM player_streak_state
            WHERE season = ? AND player_id = ? AND streak_type = ?
            """,
            (season, player_id, streak_type),
        ).fetchone()

    def _migrate_legacy_appearance_state(
        self, season: int, player_id: int, row: sqlite3.Row
    ) -> None:
        self.aggregator.conn.execute(
            """
            INSERT INTO player_streak_state (
                season, player_id, streak_type, run_index, current_value,
                ip_outs_accum, last_success_game_id, last_success_game_date,
                recorded_milestones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season, player_id, streak_type) DO UPDATE SET
                run_index = excluded.run_index,
                current_value = excluded.current_value,
                ip_outs_accum = excluded.ip_outs_accum,
                last_success_game_id = excluded.last_success_game_id,
                last_success_game_date = excluded.last_success_game_date,
                recorded_milestones = excluded.recorded_milestones
            """,
            (
                season,
                player_id,
                APPEARANCE_STREAK_TYPE,
                int(row["run_index"]),
                int(row["current_value"]),
                int(row["ip_outs_accum"]),
                row["last_success_game_id"],
                row["last_success_game_date"],
                str(row["recorded_milestones"] or ""),
            ),
        )
        self.aggregator.conn.execute(
            """
            DELETE FROM player_streak_state
            WHERE season = ? AND player_id = ? AND streak_type = ?
            """,
            (season, player_id, _LEGACY_APPEARANCE_STREAK_TYPE),
        )

    def _save_player_states(
        self,
        season: int,
        player_id: int,
        state_map: dict[str, StreakState],
    ) -> None:
        if self._replay_store:
            self._replay_store.save_player_states(player_id, state_map)
            return

        for streak_type, state in state_map.items():
            recorded = ",".join(str(v) for v in sorted(state.recorded_milestones))
            self.aggregator.conn.execute(
                """
                INSERT INTO player_streak_state (
                    season, player_id, streak_type, run_index, current_value,
                    ip_outs_accum, last_success_game_id, last_success_game_date,
                    recorded_milestones
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season, player_id, streak_type) DO UPDATE SET
                    run_index = excluded.run_index,
                    current_value = excluded.current_value,
                    ip_outs_accum = excluded.ip_outs_accum,
                    last_success_game_id = excluded.last_success_game_id,
                    last_success_game_date = excluded.last_success_game_date,
                    recorded_milestones = excluded.recorded_milestones
                """,
                (
                    season,
                    player_id,
                    streak_type,
                    state.run_index,
                    state.current,
                    state.ip_outs_accum,
                    state.last_success_game_id,
                    state.last_success_game_date,
                    recorded,
                ),
            )

    def _persist_event(
        self,
        event: StreakEvent,
        season: int,
        game_id: int,
    ) -> None:
        player_id = event.player_id
        team = event.team or None
        game_date = self._game_date(game_id)
        milestone_key = f"streak_{event.streak_type}"

        existing = self.aggregator.conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE player_id = ? AND game_id = ? AND milestone_key = ?
              AND streak_event_type = ? AND achieved_value = ?
            """,
            (
                player_id,
                game_id,
                milestone_key,
                event.event_type,
                float(event.milestone_value),
            ),
        ).fetchone()
        if existing:
            return

        description = json.dumps(
            {
                "streak_run_id": event.streak_run_id,
                "last_success_game_id": event.last_success_game_id,
                "last_success_game_date": event.last_success_game_date,
            },
            ensure_ascii=False,
        )

        self.aggregator.conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope,
                season, game_id, achieved_date, achieved_value,
                team, notes, description, is_manual,
                streak_type, streak_run_id, streak_event_type
            ) VALUES (?, ?, ?, 'streak', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                player_id,
                milestone_key,
                event.milestone_label,
                season,
                game_id,
                game_date,
                float(event.milestone_value),
                team,
                event.streak_run_id,
                description,
                event.streak_type,
                event.streak_run_id,
                event.event_type,
            ),
        )

    def _game_date(self, game_id: int) -> str:
        row = self.aggregator.conn.execute(
            "SELECT date FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        return str(row["date"]) if row else ""

    def _tracked_team_names(self) -> set[str]:
        return set(expand_tracked_teams(self.tracked_teams, self.custom_teams))

    def _team_is_tracked(self, team_name: str | None) -> bool:
        if not self.tracked_teams:
            return True
        if not team_name:
            return False
        names = self._tracked_team_names()
        if team_name in names:
            return True
        return team_name.upper() in {
            token.strip().upper() for token in self.tracked_teams if token.strip()
        }

    def _filter_game_log_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.tracked_teams:
            return rows
        tracked_names = self._tracked_team_names()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            team = str(row.get("team") or "")
            if team in tracked_names or team.upper() in {
                token.strip().upper() for token in self.tracked_teams if token.strip()
            }:
                filtered.append(row)
        return filtered


def rebuild_season_streaks(
    aggregator: Aggregator,
    season: int,
    *,
    tracked_teams: list[str] | None = None,
    custom_teams: dict[str, str] | None = None,
) -> int:
    """Clear streak state for a season and reprocess all games (admin/backfill)."""
    conn = aggregator.conn
    conn.execute("DELETE FROM player_streak_state WHERE season = ?", (season,))
    conn.execute("DELETE FROM streak_processed_games WHERE season = ?", (season,))
    conn.execute(
        """
        DELETE FROM milestone_records
        WHERE scope = 'streak' AND season = ?
        """,
        (season,),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT game_id FROM games WHERE season = ? ORDER BY date, game_id",
        (season,),
    ).fetchall()
    game_ids = [int(row["game_id"]) for row in rows]
    tracker = StreakTracker(
        aggregator,
        tracked_teams=tracked_teams,
        custom_teams=custom_teams,
    )
    events = tracker.process_new_games(game_ids, season)
    conn.commit()
    return len(events)
