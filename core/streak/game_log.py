"""Derive per-game batting/pitching flags from DB log rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BattingGameLog:
    season: int
    game_id: int
    game_date: str
    player_id: int
    player_name: str
    team: str
    ab: int
    r: int
    h: int
    rbi: int
    bb: int
    hit_by_pitch: int
    home_runs: int
    stolen_bases: int
    appeared_game: bool = True

    @property
    def batting_opportunity(self) -> bool:
        return self.ab + self.bb + self.hit_by_pitch >= 1

    @property
    def hit_game(self) -> bool:
        return self.h >= 1

    @property
    def hr_game_flag(self) -> bool:
        return self.home_runs >= 1

    @property
    def sb_game_flag(self) -> bool:
        return self.stolen_bases >= 1

    @property
    def rbi_game(self) -> bool:
        return self.rbi >= 1

    @property
    def run_game(self) -> bool:
        return self.r >= 1

    @property
    def walk_game(self) -> bool:
        return self.bb >= 1

    @property
    def on_base_game(self) -> bool:
        return self.h >= 1 or self.bb >= 1 or self.hit_by_pitch >= 1


@dataclass(frozen=True)
class PitchingGameLog:
    season: int
    game_id: int
    game_date: str
    player_id: int
    player_name: str
    team: str
    ip_outs: int
    r_allowed: int
    er_allowed: int
    is_starter: bool
    decision: str = ""

    @property
    def win_game(self) -> bool:
        return self.decision == "W"

    @property
    def save_game(self) -> bool:
        return self.decision == "S"

    @property
    def loss_game(self) -> bool:
        return self.decision == "L"

    @property
    def blown_save(self) -> bool:
        return self.decision == "BS"

    @property
    def qs_game(self) -> bool:
        return self.is_starter and self.ip_outs >= 18 and self.er_allowed <= 3

    @property
    def scoreless_appearance(self) -> bool:
        return self.r_allowed == 0


def batting_log_from_row(row: dict[str, Any], *, player_name: str = "") -> BattingGameLog:
    return BattingGameLog(
        season=int(row["season"]),
        game_id=int(row["game_id"]),
        game_date=str(row["date"]),
        player_id=int(row["player_id"]),
        player_name=player_name or str(row.get("player_name") or ""),
        team=str(row["team"]),
        ab=int(row.get("ab") or 0),
        r=int(row.get("r") or 0),
        h=int(row.get("h") or 0),
        rbi=int(row.get("rbi") or 0),
        bb=int(row.get("bb") or 0),
        hit_by_pitch=int(row.get("hit_by_pitch") or 0),
        home_runs=int(row.get("home_runs") or 0),
        stolen_bases=int(row.get("stolen_bases") or 0),
    )


def _normalize_pitching_decision(row: dict[str, Any]) -> str:
    decision = str(row.get("decision") or "").strip().upper()
    if decision == "SV":
        return "S"
    if decision:
        return decision
    if int(row.get("win") or 0):
        return "W"
    if int(row.get("loss") or 0):
        return "L"
    if int(row.get("save") or 0):
        return "S"
    return ""


def pitching_log_from_row(row: dict[str, Any], *, player_name: str = "") -> PitchingGameLog:
    return PitchingGameLog(
        season=int(row["season"]),
        game_id=int(row["game_id"]),
        game_date=str(row["date"]),
        player_id=int(row["player_id"]),
        player_name=player_name or str(row.get("player_name") or ""),
        team=str(row["team"]),
        ip_outs=int(row.get("ip_outs") or 0),
        r_allowed=int(row.get("r") or 0),
        er_allowed=int(row.get("er") or 0),
        is_starter=bool(int(row.get("is_starter") or 0)),
        decision=_normalize_pitching_decision(row),
    )
