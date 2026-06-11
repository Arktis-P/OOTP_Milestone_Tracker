"""Parse pitching notes text blocks from box scores."""

from __future__ import annotations

import re
from dataclasses import dataclass

GAME_SCORE_RE = re.compile(
    r"Game Score:\s*(.+?)\s+(-?\d+)",
    re.I,
)
WILD_PITCH_RE = re.compile(r"Wild Pitch(?:es)?\s*:\s*(.+)", re.I)
HIT_BATSMEN_RE = re.compile(r"Hit Batters?\s*:\s*(.+)", re.I)


@dataclass
class PitchingEventCounts:
    game_score: int | None = None
    wild_pitch: int = 0
    hit_batsmen: int = 0


def parse_team_pitching_notes(note_text: str) -> dict[str, PitchingEventCounts]:
    if not note_text:
        return {}

    pitching_idx = note_text.find("PITCHING")
    text = note_text[pitching_idx:] if pitching_idx >= 0 else note_text
    result: dict[str, PitchingEventCounts] = {}

    for match in GAME_SCORE_RE.finditer(text):
        name = match.group(1).strip()
        score = int(match.group(2))
        bucket = result.setdefault(name, PitchingEventCounts())
        bucket.game_score = score

    wp_match = WILD_PITCH_RE.search(text)
    if wp_match:
        for name, count in _parse_comma_names(wp_match.group(1)).items():
            bucket = result.setdefault(name, PitchingEventCounts())
            bucket.wild_pitch += count

    hb_match = HIT_BATSMEN_RE.search(text)
    if hb_match:
        for name, count in _parse_comma_names(hb_match.group(1)).items():
            bucket = result.setdefault(name, PitchingEventCounts())
            bucket.hit_batsmen += count

    return result


def get_player_pitching_counts(
    note_text: str, player_name: str
) -> PitchingEventCounts:
    return parse_team_pitching_notes(note_text).get(
        player_name, PitchingEventCounts()
    )


def _parse_comma_names(fragment: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for part in fragment.split(","):
        name = part.strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts
