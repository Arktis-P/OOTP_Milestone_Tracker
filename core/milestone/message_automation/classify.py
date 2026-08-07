"""Classify an OOTP inbox message body into an automation category.

See `docs/message_automation_field_rules.md` SS2-11 and
`tests/fixtures/messages/README.md` for the category list and the messages
that are deliberately excluded from automation ("1차 제외").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Category identifiers (also used as `ParsedMessage.category`).
CAT_TRADE = "trade"
CAT_FA = "fa_contract"
CAT_EXTENSION = "extension_contract"
CAT_INJURY = "injury"
CAT_AWARD_MVP = "award_mvp"
CAT_AWARD_CY_YOUNG = "award_cy_young"
CAT_AWARD_GREAT_GLOVE = "award_great_glove"
CAT_AWARD_PLATINUM_STICK = "award_platinum_stick"
CAT_AWARD_ROY = "award_rookie_of_year"
CAT_AWARD_PLAYER_OF_MONTH = "award_player_of_month"
CAT_AWARD_ALL_STAR = "award_all_star"
CAT_POSTSEASON_DIVISION = "postseason_division"
CAT_POSTSEASON_WORLD_SERIES = "postseason_world_series"
CAT_HALL_OF_FAME = "hall_of_fame"

# Structurally excluded categories (never recorded regardless of tracked team).
CAT_TRADE_DEADLINE = "trade_deadline_news"
CAT_RETIREMENT = "retirement"
CAT_POSTSEASON_WILDCARD = "postseason_wildcard"
CAT_POSTSEASON_PLAYOFF_CLINCH = "postseason_playoff_clinch"
CAT_AWARD_ALL_STAR_VOTING = "award_all_star_voting"
CAT_HALL_OF_FAME_VOTING = "hall_of_fame_voting"
CAT_AWARD_PLAYER_OF_WEEK = "award_player_of_week"
CAT_UNKNOWN = "unknown"

# Exclusion reasons (stable strings; part of the public/testable contract).
REASON_TRADE_DEADLINE = "trade_deadline_not_a_transaction"
REASON_RETIREMENT = "retirement_milestone_undefined"
REASON_WILDCARD = "postseason_wildcard_key_mismatch"
REASON_PLAYOFF_CLINCH = "postseason_playoff_clinch_no_key"
REASON_ALL_STAR_VOTING = "all_star_voting_not_final"
REASON_HOF_VOTING = "hall_of_fame_voting_not_final"
REASON_PLAYER_OF_WEEK = "player_of_week_not_recorded"
REASON_UNRECOGNIZED = "unrecognized_message_type"


@dataclass(frozen=True)
class Classification:
    category: str
    excluded: bool
    exclusion_reason: str | None


def classify_message(title: str, plain_text: str) -> Classification:
    haystack = f"{title}\n{plain_text}"
    lower = haystack.lower()

    if "trade deadline" in title.lower():
        return Classification(CAT_TRADE_DEADLINE, True, REASON_TRADE_DEADLINE)

    if re.search(r"\bwill retire\b", title, re.I) or "announced his retirement" in lower or "announced her retirement" in lower:
        return Classification(CAT_RETIREMENT, True, REASON_RETIREMENT)

    if "hall of fame" in lower:
        if "voting begins" in lower:
            return Classification(CAT_HALL_OF_FAME_VOTING, True, REASON_HOF_VOTING)
        if re.search(r"\binduct", lower):
            return Classification(CAT_HALL_OF_FAME, False, None)
        return Classification(CAT_UNKNOWN, True, REASON_UNRECOGNIZED)

    if "all-star" in lower:
        if "voting begins" in lower:
            return Classification(CAT_AWARD_ALL_STAR_VOTING, True, REASON_ALL_STAR_VOTING)
        if "roster" in lower:
            return Classification(CAT_AWARD_ALL_STAR, False, None)
        return Classification(CAT_UNKNOWN, True, REASON_UNRECOGNIZED)

    if "player of the week" in lower:
        return Classification(CAT_AWARD_PLAYER_OF_WEEK, True, REASON_PLAYER_OF_WEEK)

    if "most valuable player" in lower:
        return Classification(CAT_AWARD_MVP, False, None)

    if "cy young" in lower:
        return Classification(CAT_AWARD_CY_YOUNG, False, None)

    if "great glove" in lower:
        return Classification(CAT_AWARD_GREAT_GLOVE, False, None)

    if "platinum stick" in lower:
        return Classification(CAT_AWARD_PLATINUM_STICK, False, None)

    if "batter of the month" in lower or "pitcher of the month" in lower or "rookie of the month" in lower:
        return Classification(CAT_AWARD_PLAYER_OF_MONTH, False, None)

    if "rookie of the year" in lower:
        return Classification(CAT_AWARD_ROY, False, None)

    if "wild card" in title.lower():
        return Classification(CAT_POSTSEASON_WILDCARD, True, REASON_WILDCARD)

    if "division" in title.lower() and re.search(r"winner|capture|clinch|crown", title, re.I):
        return Classification(CAT_POSTSEASON_DIVISION, False, None)

    if "playoffs" in lower and re.search(r"off to the playoffs|clinch(?:ed|es|ing)? a (?:playoff|spot)", lower):
        return Classification(CAT_POSTSEASON_PLAYOFF_CLINCH, True, REASON_PLAYOFF_CLINCH)

    if "world series" in lower and (
        re.search(r"\bswept\b", lower) or re.search(r"\bchampions\b", lower)
    ):
        return Classification(CAT_POSTSEASON_WORLD_SERIES, False, None)

    if "extension" in lower:
        return Classification(CAT_EXTENSION, False, None)

    if re.search(r"front office announced the signing|reached an agreement bringing", lower):
        return Classification(CAT_FA, False, None)

    if re.search(r"\btraded\b|\bswap\b|\bacquired\b|in exchange for|agreement to deal|confirms? trade", lower):
        return Classification(CAT_TRADE, False, None)

    if re.search(
        r"injur|sidelined|strain|sustained|torn|sprained|concussion|tripped|beaned|"
        r"shuts down|setback in his recovery|day.to.day|\bdtd\b",
        lower,
    ):
        return Classification(CAT_INJURY, False, None)

    return Classification(CAT_UNKNOWN, True, REASON_UNRECOGNIZED)
