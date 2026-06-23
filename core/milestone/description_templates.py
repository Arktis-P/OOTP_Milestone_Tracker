"""Milestone description auto-generation (templates A–D)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from typing import Any

from core.milestone.definitions import MilestoneDefinition
from core.stats.ip_utils import outs_to_ip_str
from core.stats.models import AtBatData

_BATTING_GAME_TEMPLATES: frozenset[str] = frozenset({
    "batting_cumulative",
    "batting_event",
    "season_batting_stat",
    "season_batting_rate",
    "season_batting_composite",
    "season_batting_title",
    "career_batting_stat",
    "career_batting_honor",
})

_PITCHING_FULL_TEMPLATES: frozenset[str] = frozenset({
    "pitching_full",
    "season_pitching_stat",
    "season_pitching_rate",
    "season_pitching_title",
    "career_pitching_stat",
    "career_pitching_honor",
})

TEAM_GAME_TEMPLATE_MAP: dict[str, tuple[str, str]] = {
    "team_game_starter_all_hit": ("선발", "안타"),
    "team_game_starter_all_rbi": ("선발", "타점"),
    "team_game_all_hit": ("출장", "안타"),
    "team_game_all_rbi": ("출장", "타점"),
    "team_game_no_hitter": ("출장 투수", "노히터"),
    "team_game_perfect": ("출장 투수", "퍼펙트"),
}

NameResolver = Callable[[int, str], str]


def fill_description(
    milestone: MilestoneDefinition,
    context: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
    name_resolver: NameResolver | None = None,
) -> str | None:
    """Return auto-generated description or None (situational / manual / no data)."""
    template = (milestone.description_template or "").strip()
    if not template or template == "situational":
        return None

    if template in _BATTING_GAME_TEMPLATES:
        row = context.get("batting_row")
        return build_template_a(row) if row else None

    if template in _PITCHING_FULL_TEMPLATES:
        row = context.get("pitching_row")
        return build_template_b(row) if row else None

    if template == "pitching_k_only":
        row = context.get("pitching_row")
        return build_template_b(row, simplified=True) if row else None

    if template == "team_game":
        game_id = context.get("game_id")
        team = context.get("team")
        if not conn or not game_id or not team:
            return None
        return build_template_c(
            milestone.key,
            int(game_id),
            str(team),
            conn,
            name_resolver=name_resolver,
        )

    if template in ("team_season", "team_season_event"):
        game_id = context.get("game_id")
        team = context.get("team")
        if not conn or not game_id or not team:
            return None
        return build_template_d(int(game_id), str(team), conn)

    return None


def build_description_context(
    conn: sqlite3.Connection,
    *,
    game_id: int | None,
    player_id: int | None,
    team: str | None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "game_id": game_id,
        "team": team,
    }
    if game_id and player_id:
        batting = conn.execute(
            "SELECT * FROM batting_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        pitching = conn.execute(
            "SELECT * FROM pitching_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        if batting:
            ctx["batting_row"] = _row_to_dict(batting)
        if pitching:
            ctx["pitching_row"] = _row_to_dict(pitching)
    if game_id and team and not ctx.get("team"):
        ctx["team"] = team
    elif game_id and player_id and not ctx.get("team"):
        row = conn.execute(
            """
            SELECT team FROM batting_logs WHERE player_id = ? AND game_id = ?
            UNION
            SELECT team FROM pitching_logs WHERE player_id = ? AND game_id = ?
            LIMIT 1
            """,
            (player_id, game_id, player_id, game_id),
        ).fetchone()
        if row:
            ctx["team"] = _cell(row, "team", 0)
    return ctx


def build_template_a(batting_row: dict[str, Any]) -> str:
    ab = int(batting_row.get("ab") or 0)
    hits = int(batting_row.get("h") or 0)
    hr = int(batting_row.get("home_runs") or 0)
    rbi = int(batting_row.get("rbi") or 0)
    parts = [f"{ab}타수", f"{hits}안타"]
    if hr > 0:
        parts.append(f"{hr}홈런")
    if rbi > 0:
        parts.append(f"{rbi}타점")
    return " ".join(parts)


def build_template_b(pitching_row: dict[str, Any], *, simplified: bool = False) -> str:
    ip_outs = int(pitching_row.get("ip_outs") or 0)
    k = int(pitching_row.get("k") or 0)
    ip_str = outs_to_ip_str(ip_outs)
    if simplified:
        return f"{ip_str}이닝 {k}탈삼진"

    hits = int(pitching_row.get("h") or 0)
    walks = int(pitching_row.get("bb") or 0)
    er = int(pitching_row.get("er") or 0)
    hit_part = "무피안타" if hits == 0 else f"{hits}피안타"
    walk_part = "무볼넷" if walks == 0 else f"{walks}볼넷"
    er_part = "무실점" if er == 0 else f"{er}실점"
    result = _pitching_result(pitching_row)
    return f"{ip_str}이닝 {hit_part} {walk_part} {k}탈삼진 {er_part} {result}"


def _pitching_result(row: dict[str, Any]) -> str:
    decision = str(row.get("decision") or "").upper()
    if decision == "S" or int(row.get("save") or 0):
        return "세이브"
    if int(row.get("is_sho") or 0):
        return "완봉승"
    if decision == "W" or int(row.get("win") or 0):
        return "승리"
    return "투구"


def build_template_c(
    milestone_key: str,
    game_id: int,
    team: str,
    conn: sqlite3.Connection,
    *,
    name_resolver: NameResolver | None = None,
) -> str | None:
    mapping = TEAM_GAME_TEMPLATE_MAP.get(milestone_key)
    if not mapping:
        return None
    role, result = mapping
    if "투수" in role:
        names = _pitcher_names(conn, game_id, team, name_resolver)
    else:
        starters_only = milestone_key.startswith("team_game_starter")
        names = _batter_names(conn, game_id, team, starters_only, name_resolver)
    if not names:
        return None
    return f"{role}({'-'.join(names)}) 전원 {result}"


def build_template_d(game_id: int, team: str, conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT home_team, away_team, home_score, away_score
        FROM games WHERE game_id = ?
        """,
        (game_id,),
    ).fetchone()
    if not row:
        return None
    home_team = str(_cell(row, "home_team", 0) or "")
    away_team = str(_cell(row, "away_team", 1) or "")
    home_score = int(_cell(row, "home_score", 2) or 0)
    away_score = int(_cell(row, "away_score", 3) or 0)
    if team == home_team:
        my_score, opp_score = home_score, away_score
    elif team == away_team:
        my_score, opp_score = away_score, home_score
    else:
        return None
    return f"{my_score}-{opp_score} 승리"


def _batter_names(
    conn: sqlite3.Connection,
    game_id: int,
    team: str,
    starters_only: bool,
    name_resolver: NameResolver | None,
) -> list[str]:
    query = """
        SELECT bl.player_id, COALESCE(p.short_name, p.full_name) AS name
        FROM batting_logs bl
        JOIN players p ON p.player_id = bl.player_id
        WHERE bl.game_id = ? AND bl.team = ?
    """
    params: list[Any] = [game_id, team]
    if starters_only:
        query += " AND bl.is_substitute = 0"
    query += " ORDER BY bl.rowid"
    rows = conn.execute(query, params).fetchall()
    return [_resolve_name(name_resolver, int(_cell(r, "player_id", 0)), str(_cell(r, "name", 1))) for r in rows]


def _pitcher_names(
    conn: sqlite3.Connection,
    game_id: int,
    team: str,
    name_resolver: NameResolver | None,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT pl.player_id, COALESCE(p.short_name, p.full_name) AS name
        FROM pitching_logs pl
        JOIN players p ON p.player_id = pl.player_id
        WHERE pl.game_id = ? AND pl.team = ?
        ORDER BY pl.rowid
        """,
        (game_id, team),
    ).fetchall()
    return [_resolve_name(name_resolver, int(_cell(r, "player_id", 0)), str(_cell(r, "name", 1))) for r in rows]


def _resolve_name(resolver: NameResolver | None, player_id: int, english: str) -> str:
    if resolver is None:
        return english
    return resolver(player_id, english) or english


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _cell(row: Any, column: str, index: int) -> Any:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[column]
    return row[index]


# ---------------------------------------------------------------------------
# Template E — situational (inning / outs / runners / result)
# ---------------------------------------------------------------------------

_PITCH_LINE_RE = re.compile(r"^\d+-\d+:")


def build_template_situational(at_bat: AtBatData) -> str | None:
    """Generate a Korean situational description from at-bat data."""
    result_kr = _format_result_kr(at_bat)
    if not result_kr:
        return None

    inning = at_bat.inning
    half_kr = "초" if at_bat.half.upper() == "TOP" else "말"
    outs_kr = ("무사", "1사", "2사")[min(at_bat.outs_before, 2)]
    runners_kr = _format_runners(*at_bat.runners_before)

    if runners_kr:
        situation = f"{inning}회{half_kr} {outs_kr} {runners_kr}에서"
    else:
        situation = f"{inning}회{half_kr} {outs_kr}에서"

    return f"{situation} {result_kr}"


def _format_runners(first: bool, second: bool, third: bool) -> str:
    if first and second and third:
        return "만루"
    parts: list[str] = []
    if first:
        parts.append("1루")
    if second:
        parts.append("2루")
    if third:
        parts.append("3루")
    return "".join(parts)


def _count_pitches(pitch_sequence: str) -> int:
    return sum(1 for line in pitch_sequence.split("\n") if _PITCH_LINE_RE.match(line.strip()))


def _count_rbi(at_bat: AtBatData) -> int:
    """Count RBI: exact for HRs, approximate for hits by counting scoring events."""
    r = at_bat.result.lower()
    if "home run" in r:
        return sum(at_bat.runners_before) + 1
    # For other hits: count "X scores" and "Runner from 3rd ... SAFE" lines
    rbi = 0
    seq = at_bat.pitch_sequence
    found_result = False
    for line in seq.split("\n"):
        stripped = line.strip()
        if not found_result:
            if stripped.isupper() or (
                _PITCH_LINE_RE.match(stripped) and at_bat.result.lower() in stripped.lower()
            ):
                found_result = True
        else:
            if "scores" in stripped.lower():
                rbi += 1
            elif re.search(r"runner from.*tries for home.*safe", stripped, re.I):
                rbi += 1
    return rbi


def _format_result_kr(at_bat: AtBatData) -> str:
    r = at_bat.result.lower()
    seq = at_bat.pitch_sequence

    if r == "single":
        rbi = _count_rbi(at_bat)
        return f"{rbi}타점 1루타" if rbi > 0 else "1루타"
    if r == "double":
        rbi = _count_rbi(at_bat)
        return f"{rbi}타점 2루타" if rbi > 0 else "2루타"
    if r == "triple":
        rbi = _count_rbi(at_bat)
        return f"{rbi}타점 3루타" if rbi > 0 else "3루타"
    if "home run" in r:
        rbi = _count_rbi(at_bat)
        if rbi == 1:
            return "솔로 홈런"
        return f"{rbi}점 홈런"
    if r == "strikeout":
        pitches = _count_pitches(seq)
        pitch_str = f"{pitches}구 " if pitches > 0 else ""
        if "swinging" in seq.lower():
            return f"{pitch_str}헛스윙 삼진"
        return f"{pitch_str}루킹 삼진"
    if r in ("walk", "hit by pitch"):
        pitches = _count_pitches(seq)
        pitch_str = f"{pitches}구 " if pitches > 0 else ""
        return f"{pitch_str}볼넷" if r == "walk" else f"{pitch_str}몸맞는 볼"
    return ""
