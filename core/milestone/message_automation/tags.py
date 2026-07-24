"""OOTP inbox message tag parsing (`<Text:kind#id>`) and tracked-team matching.

Message bodies embed references like ``<Yordan Alvarez:player#39226>`` or
``<Houston Astros:team#12>``. This module extracts those tags, builds a plain
text rendering for phrase-based regexes, and resolves player/team display
names from the tag occurrences (see `docs/message_automation_field_rules.md`
S1.2/S1.3 for the "use the tag id first" rule).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.stats.team_filter import MLB_ABBR_TO_NAME

TAG_RE = re.compile(r"<([^<>:]+):([A-Za-z_]+)#(\w+)>")


@dataclass(frozen=True)
class MessageTag:
    text: str
    kind: str
    ref_id: str
    start: int
    end: int

    @property
    def int_id(self) -> int | None:
        return int(self.ref_id) if self.ref_id.isdigit() else None


def parse_tags(raw_text: str) -> list[MessageTag]:
    """Extract all `<Text:kind#id>` tags from a raw message body, in order."""
    return [
        MessageTag(text=m.group(1), kind=m.group(2), ref_id=m.group(3), start=m.start(), end=m.end())
        for m in TAG_RE.finditer(raw_text)
    ]


def render_plain_text(raw_text: str) -> str:
    """Replace every tag with its display text, for phrase/date/number regexes."""
    return TAG_RE.sub(lambda m: m.group(1), raw_text)


def _display_variants(tags: list[MessageTag], kind: str) -> dict[int, list[str]]:
    variants: dict[int, list[str]] = {}
    for tag in tags:
        if tag.kind != kind or tag.int_id is None:
            continue
        seen = variants.setdefault(tag.int_id, [])
        if tag.text not in seen:
            seen.append(tag.text)
    return variants


def player_name_variants(tags: list[MessageTag]) -> dict[int, list[str]]:
    return _display_variants(tags, "player")


def team_name_variants(tags: list[MessageTag]) -> dict[int, list[str]]:
    return _display_variants(tags, "team")


def canonical_player_name(variants: dict[int, list[str]], player_id: int) -> str:
    """First-mentioned display text (usually the fullest name)."""
    names = variants.get(player_id)
    return names[0] if names else str(player_id)


def canonical_team_name(variants: dict[int, list[str]], team_id: int) -> str:
    """Longest display variant (prefers "Detroit Tigers" over "Detroit")."""
    names = variants.get(team_id)
    candidate = max(names, key=len) if names else str(team_id)
    matches = {
        full_name
        for full_name in MLB_ABBR_TO_NAME.values()
        if (
            full_name.lower().startswith(candidate.lower() + " ")
            or full_name.lower().endswith(" " + candidate.lower())
        )
    }
    return matches.pop() if len(matches) == 1 else candidate


def player_ref(name: str, player_id: int) -> str:
    """Format a name so `manual_entry.resolve_player_id` uses the id directly."""
    return f"{name} (#{player_id})"


def team_name_matches(candidate: str, tracked: str) -> bool:
    """True if `candidate` (a tag's team text) refers to `tracked`.

    Message tags alternate between short ("Seoul") and full ("Seoul Yukies")
    team names for the same numeric team id, so exact string equality is too
    strict. We accept exact match or a whole-word prefix in either direction
    ("Seoul" is a prefix of "Seoul Yukies") while rejecting look-alikes such
    as a minor-league affiliate ("Seoul (FCL) Yukies").
    """
    c = candidate.strip().lower()
    t = tracked.strip().lower()
    if not c or not t:
        return False
    if c == t:
        return True
    if ("(" in c) != ("(" in t):
        return False
    return c.startswith(t + " ") or t.startswith(c + " ")


def is_tracked_team_name(candidate: str, tracked_teams: list[str]) -> bool:
    if not tracked_teams:
        return True
    return any(team_name_matches(candidate, tracked) for tracked in tracked_teams)


def preferred_tracked_team_name(candidate: str, tracked_teams: list[str]) -> str:
    """Prefer a configured full name when a tag uses a short variant."""

    matches = [
        tracked
        for tracked in tracked_teams
        if team_name_matches(candidate, tracked)
    ]
    return max(matches, key=len) if matches else candidate


def team_abbreviation_candidates(tracked: str) -> set[str]:
    """Plausible short codes for a tracked team name (best-effort).

    Used only for the all-star roster message, whose position lines use a
    bare parenthetical code (e.g. ``(SY)``) instead of a `<Team:team#id>`
    tag. Not a substitute for a real team abbreviation registry.
    """
    words = [w for w in re.split(r"[\s]+", tracked.strip()) if w]
    codes: set[str] = set()
    if len(words) >= 2:
        codes.add("".join(w[0] for w in words if w[0].isalpha()).upper())
    if len(words) == 1 and 2 <= len(words[0]) <= 4:
        codes.add(words[0].upper())
    return codes


def is_tracked_team_abbreviation(abbr: str, tracked_teams: list[str]) -> bool:
    abbr_upper = abbr.strip().upper()
    if not abbr_upper:
        return False
    return any(abbr_upper in team_abbreviation_candidates(t) for t in tracked_teams)
