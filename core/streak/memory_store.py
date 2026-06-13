"""In-memory streak state for season replay (export)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.streak.engine import StreakState


@dataclass
class InMemoryStreakStore:
    states: dict[tuple[int, str], StreakState] = field(default_factory=dict)

    def load_player_states(
        self,
        player_id: int,
        policies: dict,
    ) -> dict[str, StreakState]:
        state_map: dict[str, StreakState] = {}
        for streak_type in policies:
            state_map[streak_type] = self.states.get(
                (player_id, streak_type), StreakState()
            )
        return state_map

    def save_player_states(
        self,
        player_id: int,
        state_map: dict[str, StreakState],
    ) -> None:
        for streak_type, state in state_map.items():
            self.states[(player_id, streak_type)] = state

    def active_players(self, streak_type: str) -> list[int]:
        players = {
            player_id
            for (player_id, st_type), state in self.states.items()
            if st_type == streak_type and state.current > 0
        }
        return sorted(players)
