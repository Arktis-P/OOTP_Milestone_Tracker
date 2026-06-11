"""Parse batting notes text blocks from box scores."""

from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_PATTERNS: dict[str, list[str]] = {
    "doubles": [r"Doubles\s*:"],
    "triples": [r"Triples\s*:"],
    "home_runs": [r"Home Runs\s*:"],
    "stolen_bases": [r"SB\s*:", r"Stolen Bases\s*:"],
    "hit_by_pitch": [r"Hit by Pitch\s*:", r"HBP\s*:"],
    "gidp": [r"GIDP\s*:"],
}

NEXT_SECTION_RE = re.compile(
    r"^(BATTING|BASERUNNING|FIELDING|Total Bases|2-out RBI|Team LOB|"
    r"Runners left|Doubles|Triples|Home Runs|SB|Stolen Bases|Hit by Pitch|GIDP|PB)\s*:?",
    re.I | re.M,
)

INNING_DETAIL_RE = re.compile(
    r"\((\d+)\s*,\s*(\d+)(?:st|nd|rd|th)\s+Inning",
    re.I,
)
SEASON_ONLY_RE = re.compile(r"^\((\d+)\)\s*,?$")
NAME_TRAILING_COUNT_RE = re.compile(r"^(.+?)\s+(\d+)\s*$")
INLINE_OUTSIDE_DETAIL_RE = re.compile(r"^(.+?)\s+(\d+)\s+\((.+)\)\s*,?$")
INLINE_NAME_DETAIL_RE = re.compile(r"^(.+?)\s+\((.+)\)\s*,?$")


@dataclass
class BattingEventCounts:
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    stolen_bases: int = 0
    hit_by_pitch: int = 0
    gidp: int = 0


def parse_team_batting_notes(note_text: str) -> dict[str, BattingEventCounts]:
    """Return event counts keyed by box-score short player name."""
    if not note_text:
        return {}

    batting_idx = note_text.find("BATTING")
    text = note_text[batting_idx:] if batting_idx >= 0 else note_text

    result: dict[str, BattingEventCounts] = {}

    for field_name, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            section_body = text[match.end() :]
            end_match = NEXT_SECTION_RE.search(section_body)
            if end_match:
                section_body = section_body[: end_match.start()]
            for name, count in _parse_section_entries(section_body, field_name).items():
                bucket = result.setdefault(name, BattingEventCounts())
                setattr(bucket, field_name, getattr(bucket, field_name) + count)
            break

    return result


def get_player_event_counts(
    note_text: str, player_name: str
) -> BattingEventCounts:
    all_counts = parse_team_batting_notes(note_text)
    return all_counts.get(player_name, BattingEventCounts())


def _parse_section_entries(section_text: str, field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    lines = [line.strip().rstrip(",") for line in section_text.splitlines()]
    lines = [line for line in lines if line]

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not line or line.startswith("(") or NEXT_SECTION_RE.match(line):
            idx += 1
            continue

        if "," in line and "(" not in line:
            for part in line.split(","):
                name = part.strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
            idx += 1
            continue

        name_line, detail_line, consumed = _split_entry_line(line, lines, idx)
        count = _resolve_game_event_count(name_line, detail_line, field_name)
        name = _extract_player_name(name_line)
        counts[name] = counts.get(name, 0) + count
        idx += consumed

    return counts


def _split_entry_line(
    line: str, lines: list[str], idx: int
) -> tuple[str, str, int]:
    outside_match = INLINE_OUTSIDE_DETAIL_RE.match(line)
    if outside_match:
        name = outside_match.group(1).strip()
        outside = outside_match.group(2)
        detail = f"({outside_match.group(3)})"
        return f"{name} {outside}", detail, 1

    inline_match = INLINE_NAME_DETAIL_RE.match(line)
    if inline_match:
        return inline_match.group(1).strip(), f"({inline_match.group(2)})", 1

    detail = (
        lines[idx + 1]
        if idx + 1 < len(lines) and lines[idx + 1].startswith("(")
        else ""
    )
    return line, detail, 2 if detail else 1


def _extract_player_name(line: str) -> str:
    match = NAME_TRAILING_COUNT_RE.match(line)
    if match:
        return match.group(1).strip()
    return line.strip()


def _resolve_game_event_count(name_line: str, detail_line: str, field_name: str) -> int:
    """Resolve per-game event count from name + detail lines.

    Formats:
    - ``R. Grichuk 2 (5, 6th Inning ...)`` → game=2 (outside), 5=season in parens
    - ``J. Lee 3 (15)`` (SB) → game=3, 15=season steals
    - ``R. Grichuk`` + ``(1, 6th Inning ...)`` → game=1 (season counter in parens)
    - ``K. Tucker`` + ``(2, 5th Inning ...)`` (HR) → game=2 when N != inning number
    - ``J. Lee`` + ``(1)`` (SB) → game=1
    """
    outside_match = NAME_TRAILING_COUNT_RE.match(name_line)
    outside_count = int(outside_match.group(2)) if outside_match else None

    if not detail_line:
        return outside_count or 1

    if field_name == "stolen_bases":
        season_match = SEASON_ONLY_RE.match(detail_line.strip())
        if season_match:
            return outside_count if outside_count is not None else 1
        return outside_count or 1

    inning_match = INNING_DETAIL_RE.search(detail_line)
    if inning_match:
        first_num = int(inning_match.group(1))
        inning_num = int(inning_match.group(2))

        if outside_count is not None:
            return outside_count

        if first_num == inning_num:
            return 1

        if field_name == "home_runs" and first_num != inning_num:
            return first_num

        return 1

    paren_match = re.match(r"\((\d+)", detail_line)
    if paren_match:
        return outside_count if outside_count is not None else 1

    return outside_count or 1
