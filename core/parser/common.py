"""Shared parser utilities."""

from __future__ import annotations

import re
from datetime import datetime


class ParserError(Exception):
    """Raised when an OOTP file cannot be parsed."""


PLAYER_ID_RE = re.compile(r"player_(\d+)\.html")
TEAM_ID_RE = re.compile(r"team_(\d+)\.html")
GAME_BOX_ID_RE = re.compile(r"game_box_(\d+)\.html", re.I)
GAME_LOG_ID_RE = re.compile(r"log_(\d+)\.html", re.I)
DATE_MDY_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
GAME_ID_RE = re.compile(r"GAME ID:\s*(\d+)", re.I)
TEAM_RECORD_RE = re.compile(r"^(.+?)\s*\((\d+-\d+)\)\s*$")
SUB_LABEL_RE = re.compile(r"^([a-z])-", re.I)
DECISION_RE = re.compile(r"\b(W|L|SV|BS|S)\s*\(([^)]+)\)")
HOLD_RE = re.compile(r"\bH\s*\((\d+)\)")
INNING_HEADER_RE = re.compile(r"(TOP|BOTTOM)\s+OF\s+THE\s+(\d+)(?:ST|ND|RD|TH)?", re.I)
INNING_SUMMARY_RE = re.compile(
    r"(\d+)\s+run[s]?,\s*(\d+)\s+hit[s]?,\s*(\d+)\s+error[s]?,\s*(\d+)\s+left on base;\s*"
    r"(.+?)\s+(\d+)\s*-\s*(.+?)\s+(\d+)",
    re.I,
)
EV_RE = re.compile(r"EV\s+(\d+)\s+MPH", re.I)
DISTANCE_RE = re.compile(r"Distance\s*:\s*(\d+)\s*ft", re.I)
HIT_TYPE_RE = re.compile(r"\((Line Drive|Flyball|Groundball|Popup|Bunt)[^)]*\)", re.I)


def extract_player_id(href: str | None) -> int | None:
    if not href:
        return None
    match = PLAYER_ID_RE.search(href)
    return int(match.group(1)) if match else None


def extract_team_id(href: str | None) -> int | None:
    if not href:
        return None
    match = TEAM_ID_RE.search(href)
    return int(match.group(1)) if match else None


def parse_ip(ip_str: str) -> float:
    text = ip_str.strip()
    if not text:
        return 0.0
    parts = text.split(".")
    whole = int(parts[0])
    if len(parts) == 1:
        return float(whole)
    fraction = int(parts[1])
    return whole + fraction / 3.0


def parse_date_iso(raw: str) -> str:
    match = DATE_MDY_RE.search(raw)
    if not match:
        raise ParserError(f"Cannot parse date: {raw}")
    month, day, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def parse_game_id_from_filename(filename: str, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(filename)
    return int(match.group(1)) if match else None


def parse_int(value: str, default: int = 0) -> int:
    text = value.strip().replace(",", "")
    if not text or text.upper() == "X":
        return default
    try:
        return int(text)
    except ValueError:
        return default


def parse_float(value: str, default: float = 0.0) -> float:
    text = value.strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def normalize_result(raw: str) -> str:
    text = raw.strip()
    upper = text.upper()

    if "HOME RUN" in upper or "GRAND SLAM" in upper:
        return "Home Run"
    if upper == "SINGLE":
        return "Single"
    if upper == "DOUBLE":
        return "Double"
    if upper == "TRIPLE":
        return "Triple"
    if "STRIKES OUT" in upper or "STRIKEOUT" in upper:
        return "Strikeout"
    if "BASE ON BALLS" in upper or upper == "WALK":
        return "Walk"
    if "REACHED ON ERROR" in upper:
        return "Error"
    if "GROUND" in upper and "DOUBLE PLAY" in upper:
        return "Double Play"
    if "FLY OUT" in upper or "LINE OUT" in upper or "POP OUT" in upper:
        return "Fly Out"
    if "GROUND OUT" in upper or "GROUNDED OUT" in upper:
        return "Ground Out"
    if "FIELDERS CHOICE" in upper:
        return "Fielders Choice"
    if "HIT BY PITCH" in upper:
        return "Hit By Pitch"
    return text


def extract_hit_type(text: str) -> str:
    match = HIT_TYPE_RE.search(text)
    if not match:
        return ""
    return match.group(1).title()


def extract_exit_velocity(text: str) -> float | None:
    match = EV_RE.search(text)
    return float(match.group(1)) if match else None


def extract_distance(text: str) -> int | None:
    match = DISTANCE_RE.search(text)
    return int(match.group(1)) if match else None


def parse_team_record(cell_text: str) -> tuple[str, str]:
    text = cell_text.strip()
    text = re.sub(r"\s+", " ", text)
    match = TEAM_RECORD_RE.match(text)
    if match:
        return match.group(1).strip(), match.group(2)
    return text, ""


def cell_text_with_lines(td) -> str:
    return td.get_text("\n", strip=True)
