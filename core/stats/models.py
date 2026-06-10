"""Player, team, and game log data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Player:
    id: Optional[int] = None
    name: str = ""
    team: str = ""
    position: str = ""
    bats: str = ""
    throws: str = ""


@dataclass
class BattingLog:
    player_id: Optional[int] = None
    player_name: str = ""
    game_date: str = ""
    season: int = 0
    ab: int = 0
    h: int = 0
    hr: int = 0
    rbi: int = 0
    bb: int = 0
    so: int = 0
    sb: int = 0
    r: int = 0
    doubles: int = 0
    triples: int = 0


@dataclass
class PitchingLog:
    player_id: Optional[int] = None
    player_name: str = ""
    game_date: str = ""
    season: int = 0
    ip: float = 0.0
    h: int = 0
    er: int = 0
    bb: int = 0
    so: int = 0
    w: int = 0
    l: int = 0
    sv: int = 0


@dataclass
class GameLog:
    game_date: str = ""
    season: int = 0
    home_team: str = ""
    away_team: str = ""
    batting: list[BattingLog] = field(default_factory=list)
    pitching: list[PitchingLog] = field(default_factory=list)
