"""Public parsing entry point: OOTP message text -> structured `ParsedMessage`."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import date

from . import classify, extract
from .extract import Form
from .tags import (
    MessageTag,
    canonical_player_name,
    parse_tags,
    player_name_variants,
    render_plain_text,
)

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# Categories with no season-end fallback date (field rules S1.4: the
# YYYY-12-31 default is scoped to awards/postseason/HOF only).
_NO_DATE_FALLBACK_CATEGORIES = frozenset(
    {classify.CAT_TRADE, classify.CAT_FA, classify.CAT_EXTENSION, classify.CAT_INJURY}
)


@dataclass(frozen=True)
class ParsedMessage:
    """Structured result of parsing one OOTP inbox message.

    `excluded` + `exclusion_reason` are directly testable: every message that
    should not create a `milestone_records` row -- whether a "1차 제외"
    category from `tests/fixtures/messages/README.md` or one whose tracked
    team is not involved -- has `excluded=True` and `forms == []`. Otherwise
    `forms` holds ready-to-record `core.milestone.manual_entry` form objects
    (see `recorder.record_parsed_message` for how they get persisted).
    """

    category: str
    title: str
    excluded: bool
    exclusion_reason: str | None
    forms: list[Form] = field(default_factory=list)
    source_id: str | None = None
    player_names: dict[int, str] = field(default_factory=dict)


def _extract_body_year(plain_text: str) -> int | None:
    m = _YEAR_RE.search(plain_text)
    return int(m.group(0)) if m else None


def _resolve_season(
    *, category: str, plain_text: str, season_hint: int | None, message_date: date | None
) -> int | None:
    # A Hall of Fame bio's "retired in 2026" is not the induction year, so
    # HOF deliberately skips the body-year scan (field rules S8).
    body_year = None if category == classify.CAT_HALL_OF_FAME else _extract_body_year(plain_text)
    if body_year is not None:
        return body_year
    if season_hint is not None:
        return season_hint
    if message_date is not None:
        return message_date.year
    return None


def _resolve_achieved_date(*, category: str, season: int | None, message_date: date | None) -> date | None:
    if message_date is not None:
        return message_date
    if category not in _NO_DATE_FALLBACK_CATEGORIES and season is not None:
        return date(season, 12, 31)
    return None


def parse_message(
    text: str,
    *,
    tracked_teams: list[str] | None = None,
    message_date: date | None = None,
    season_hint: int | None = None,
    source_id: str | None = None,
) -> ParsedMessage:
    """Parse one raw OOTP message body into a structured, recordable result.

    Args:
        text: Full message text, exactly as stored in an OOTP
            `messages/messageN.txt` file (title on the first line).
        tracked_teams: Same convention as `MilestoneChecker(tracked_teams=...)`.
            Only messages involving one of these teams produce forms
            (field rules S1.3). Team name matching accepts short/full tag
            variants of the same team (see `tags.team_name_matches`).
        message_date: The message's metadata date (from `messages.dat`,
            not yet parsed by this module). When omitted, award/postseason/
            HOF categories fall back to a season-end default date; trade/FA/
            extension/injury categories have no such fallback and are
            excluded (field rules S1.4).
        season_hint: An optional pre-resolved season (e.g. the caller's own
            `season_if_in_season(conn, message_date)` or
            `settings.current_season`), used only when the message body
            itself states no year.
        source_id: Optional message identifier (e.g. ``"message1433"``),
            stored in `notes` as ``source:<id>`` where the form has a notes
            field to spare (field rules S1.1: "비고 ... 소스 메시지 ID 등").

    Returns:
        A `ParsedMessage`. Check `.excluded` before calling
        `recorder.record_parsed_message`.
    """

    tracked_teams = list(tracked_teams or [])
    resolved_source_id = source_id or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""

    tags = parse_tags(text)
    variants = player_name_variants(tags)
    player_names = {
        player_id: canonical_player_name(variants, player_id)
        for player_id in variants
    }
    plain_text = render_plain_text(text)

    classification = classify.classify_message(title, plain_text)
    category = classification.category

    if classification.excluded:
        return ParsedMessage(
            category,
            title,
            True,
            classification.exclusion_reason,
            [],
            resolved_source_id,
            player_names,
        )

    season = _resolve_season(
        category=category, plain_text=plain_text, season_hint=season_hint, message_date=message_date
    )
    achieved_date = _resolve_achieved_date(category=category, season=season, message_date=message_date)
    notes = f"source:{resolved_source_id}"

    result = _dispatch(
        category=category,
        title=title,
        raw_text=text,
        plain_text=plain_text,
        tags=tags,
        tracked_teams=tracked_teams,
        season=season,
        achieved_date=achieved_date,
        message_date=message_date,
        notes=notes,
    )

    forms = [_append_source_note(form, notes) for form in result.forms]
    excluded = not forms
    return ParsedMessage(
        category,
        title,
        excluded,
        result.exclusion_reason if excluded else None,
        forms,
        resolved_source_id,
        player_names,
    )


def _append_source_note(form: Form, source_note: str) -> Form:
    current = str(getattr(form, "notes", "") or "").strip()
    if source_note in current:
        return form
    combined = f"{source_note}; {current}" if current else source_note
    return replace(form, notes=combined)


def _dispatch(
    *,
    category: str,
    title: str,
    raw_text: str,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
    message_date: date | None,
    notes: str | None,
) -> extract.ExtractResult:
    if category == classify.CAT_TRADE:
        return extract.extract_trade(
            raw_text, tags, tracked_teams=tracked_teams, season=season, achieved_date=achieved_date, notes=notes
        )
    if category in (classify.CAT_FA, classify.CAT_EXTENSION):
        return extract.extract_fa_or_extension(
            is_extension=category == classify.CAT_EXTENSION,
            plain_text=plain_text,
            tags=tags,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
            notes=notes,
        )
    if category == classify.CAT_INJURY:
        return extract.extract_injury(
            plain_text=plain_text,
            tags=tags,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
            notes=notes,
        )
    if category in (classify.CAT_AWARD_MVP, classify.CAT_AWARD_CY_YOUNG, classify.CAT_AWARD_ROY):
        return extract.extract_vote_award(
            category=category,
            raw_text=raw_text,
            plain_text=plain_text,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
        )
    if category in (classify.CAT_AWARD_GREAT_GLOVE, classify.CAT_AWARD_PLATINUM_STICK):
        return extract.extract_position_list_award(
            category=category,
            raw_text=raw_text,
            plain_text=plain_text,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
        )
    if category == classify.CAT_AWARD_PLAYER_OF_MONTH:
        return extract.extract_player_of_month(
            plain_text=plain_text,
            tags=tags,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
            message_date=message_date,
        )
    if category == classify.CAT_AWARD_ALL_STAR:
        return extract.extract_all_star(
            title=title, raw_text=raw_text, tracked_teams=tracked_teams, season=season, achieved_date=achieved_date
        )
    if category == classify.CAT_POSTSEASON_DIVISION:
        return extract.extract_division(
            title=title,
            plain_text=plain_text,
            tags=tags,
            tracked_teams=tracked_teams,
            season=season,
            achieved_date=achieved_date,
        )
    if category == classify.CAT_POSTSEASON_WORLD_SERIES:
        return extract.extract_world_series(
            plain_text=plain_text, tags=tags, tracked_teams=tracked_teams, season=season, achieved_date=achieved_date
        )
    if category == classify.CAT_HALL_OF_FAME:
        return extract.extract_hall_of_fame(
            plain_text=plain_text, tags=tags, tracked_teams=tracked_teams, season=season, achieved_date=achieved_date
        )
    return extract.ExtractResult([], classify.REASON_UNRECOGNIZED)
