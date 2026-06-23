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
class ParsedGameLog:
    """Legacy aggregate used by aggregator (Phase 2)."""

    game_date: str = ""
    season: int = 0
    home_team: str = ""
    away_team: str = ""
    batting: list[BattingLog] = field(default_factory=list)
    pitching: list[PitchingLog] = field(default_factory=list)


# Phase 1 parsed box score / game log structures


@dataclass
class GameMeta:
    game_id: int
    date: str
    away_team: str
    home_team: str
    away_score: int
    home_score: int
    away_team_id: int | None = None
    home_team_id: int | None = None
    away_record: str = ""
    home_record: str = ""
    away_innings: list[int] = field(default_factory=list)
    home_innings: list[int] = field(default_factory=list)
    away_hits: int = 0
    home_hits: int = 0
    away_errors: int = 0
    home_errors: int = 0
    ballpark: str = ""
    attendance: int = 0
    game_time: str = ""


@dataclass
class LineScore:
    away_team: str
    home_team: str
    away_record: str
    home_record: str
    away_innings: list[int]
    home_innings: list[int]
    away_score: int
    home_score: int
    away_hits: int
    home_hits: int
    away_errors: int
    home_errors: int
    away_team_id: int | None = None
    home_team_id: int | None = None


@dataclass
class BatterLine:
    player_name: str
    player_id: int
    team: str
    position: str
    is_substitute: bool
    sub_label: str
    ab: int
    r: int
    h: int
    rbi: int
    bb: int
    k: int
    lob: int
    avg: float
    season_hr: int
    season_rbi: int
    team_id: int | None = None


@dataclass
class PitcherLine:
    player_name: str
    player_id: int
    team: str
    decision: str
    decision_record: str
    ip: float
    h: int
    r: int
    er: int
    bb: int
    k: int
    hr: int
    bf: int
    pi: int
    era: float
    hold_earned: bool = False
    season_holds: int = 0
    team_id: int | None = None


@dataclass
class GameNotes:
    player_of_game: str = ""
    player_of_game_id: int | None = None
    ballpark: str = ""
    weather: str = ""
    start_time: str = ""
    game_time: str = ""
    attendance: int = 0
    special_notes: str = ""


@dataclass
class BoxscoreData:
    meta: GameMeta
    away_batting: list[BatterLine]
    home_batting: list[BatterLine]
    away_pitching: list[PitcherLine]
    home_pitching: list[PitcherLine]
    away_batting_notes: str
    home_batting_notes: str
    away_pitching_notes: str = ""
    home_pitching_notes: str = ""
    game_notes: GameNotes = field(default_factory=GameNotes)


@dataclass
class ImportResult:
    game_id: int
    skipped: bool = False
    error: str | None = None


@dataclass
class BatchImportResult:
    imported: int = 0
    skipped: int = 0
    skipped_mtime: int = 0
    skipped_existing: int = 0
    skipped_non_mlb: int = 0
    errors: list[ImportResult] = field(default_factory=list)
    total_scanned: int = 0
    candidates: int = 0
    imported_game_ids: list[int] = field(default_factory=list)
    refreshed_game_ids: list[int] = field(default_factory=list)
    scan_elapsed_s: float = 0.0
    import_elapsed_s: float = 0.0


@dataclass
class InningSummary:
    runs: int
    hits: int
    errors: int
    lob: int
    away_score: int
    home_score: int
    away_team: str = ""
    home_team: str = ""


@dataclass
class AtBatData:
    inning: int
    half: str
    batter_name: str
    batter_id: int
    batter_hand: str
    pitcher_name: str = ""
    pitcher_id: int | None = None
    pitch_sequence: str = ""
    result: str = ""
    hit_type: str = ""
    exit_velocity: float | None = None
    distance: int | None = None
    outs_before: int = 0
    runners_before: tuple[bool, bool, bool] = (False, False, False)


@dataclass
class InningData:
    inning_num: int
    half: str
    batting_team: str
    pitching_team: str
    at_bats: list[AtBatData] = field(default_factory=list)
    summary: InningSummary | None = None


@dataclass
class GameLogData:
    game_id: int
    date: str
    away_team: str
    home_team: str
    innings: list[InningData] = field(default_factory=list)
