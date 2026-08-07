"""Per-category field extraction: message text -> existing manual-entry forms.

Each `extract_*` function turns the tagged message body into zero or more of
the *existing* `core.milestone.manual_entry` form dataclasses
(`ManualTransferFormData` / `ManualInjuryFormData` / `ManualMilestoneFormData`).
Recording then goes through the existing `MilestoneChecker.record_manual_*`
methods unchanged (see `recorder.py`) -- this module only builds the forms.

Field formulas follow `docs/message_automation_field_rules.md`. Two rules are
deliberately NOT implemented here (see SS3/S4/S13 of that document and
S13's TODO list):

- FA/extension option-and-opt-out years ("10+2년") -- not present in the
  OOTP news body, so only guaranteed years are parsed.
- Injury-name Korean translation (e.g. "sprained ankle" -> "발목 염좌") --
  reserved for a future Gemini-backed lookup. Injury labels stay in English;
  only the *duration* is normalized to Korean, which is plain unit parsing
  rather than translation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    build_injury_description,
    build_trade_description,
)

from . import classify
from .tags import (
    MessageTag,
    canonical_player_name,
    canonical_team_name,
    is_tracked_team_name,
    player_name_variants,
    player_ref,
    preferred_tracked_team_name,
    team_abbreviation_candidates,
    team_name_variants,
)

Form = ManualTransferFormData | ManualInjuryFormData | ManualMilestoneFormData


@dataclass(frozen=True)
class ExtractResult:
    forms: list[Form]
    exclusion_reason: str | None = None


# --------------------------------------------------------------------------
# Trade
# --------------------------------------------------------------------------

_TRADE_CONNECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("exchange", re.compile(r"\bin exchange for\b", re.I)),
    ("receiving", re.compile(r"\breceiving\b", re.I)),
    ("return", re.compile(r"\bin return\b", re.I)),
    ("for", re.compile(r"\bfor\s+(?=\d+-year|<)", re.I)),
]
_CASH_RE = re.compile(r"(\$[\d,]+)\s+in cash\b", re.I)


def _find_trade_split(raw_text: str) -> tuple[int, str] | None:
    for kind, pattern in _TRADE_CONNECTORS:
        m = pattern.search(raw_text)
        if m:
            return m.start(), kind
    return None


def _find_cash_mentions(raw_text: str, split_pos: int) -> tuple[list[str], list[str]]:
    before: list[str] = []
    after: list[str] = []
    for m in _CASH_RE.finditer(raw_text):
        (before if m.start() < split_pos else after).append(m.group(1))
    return before, after


def _unique_player_tags(
    tags: list[MessageTag], *, excluding_ids: set[int] | None = None
) -> list[MessageTag]:
    excluded = excluding_ids or set()
    seen: set[int] = set()
    unique: list[MessageTag] = []
    for tag in tags:
        if tag.int_id is None or tag.int_id in excluded or tag.int_id in seen:
            continue
        seen.add(tag.int_id)
        unique.append(tag)
    return unique


def extract_trade(
    raw_text: str,
    tags: list[MessageTag],
    *,
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
    notes: str | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    player_tags = [t for t in tags if t.kind == "player" and t.int_id is not None]
    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    distinct_team_ids: list[int] = []
    for t in team_tags:
        if t.int_id not in distinct_team_ids:
            distinct_team_ids.append(t.int_id)
    if len(distinct_team_ids) < 2 or not player_tags:
        return ExtractResult([], "unparseable_trade_structure")

    split = _find_trade_split(raw_text)
    if split is None:
        return ExtractResult([], "unparseable_trade_structure")
    split_pos, kind = split

    group1 = _unique_player_tags([t for t in player_tags if t.start < split_pos])
    group1_ids = {int(t.int_id) for t in group1 if t.int_id is not None}
    group2 = _unique_player_tags(
        [t for t in player_tags if t.start > split_pos],
        excluding_ids=group1_ids,
    )
    if not group1 or not group2:
        return ExtractResult([], "unparseable_trade_structure")

    teams_before = [t for t in team_tags if t.start < split_pos]
    if not teams_before:
        return ExtractResult([], "unparseable_trade_structure")
    team_near_id = teams_before[-1].int_id
    other_ids = [tid for tid in distinct_team_ids if tid != team_near_id]
    if not other_ids:
        return ExtractResult([], "unparseable_trade_structure")
    other_id = other_ids[0]

    # "to <Team>" (return/for) points group1 at the near team; "<Team>
    # receiving" / "from <Team> in exchange for" points group2 at it instead.
    if kind in ("return", "for"):
        team_group1_id, team_group2_id = team_near_id, other_id
    else:
        team_group1_id, team_group2_id = other_id, team_near_id

    team_variants = team_name_variants(tags)
    team_group1_name = canonical_team_name(team_variants, team_group1_id)
    team_group2_name = canonical_team_name(team_variants, team_group2_id)
    team_group1_name = preferred_tracked_team_name(team_group1_name, tracked_teams)
    team_group2_name = preferred_tracked_team_name(team_group2_name, tracked_teams)

    tracked_is_group1 = is_tracked_team_name(team_group1_name, tracked_teams)
    tracked_is_group2 = is_tracked_team_name(team_group2_name, tracked_teams)
    if not tracked_is_group1 and not tracked_is_group2:
        return ExtractResult([], "tracked_team_not_involved")

    if tracked_is_group1:
        joining, leaving = group1, group2
        join_team, counterpart_team = team_group1_name, team_group2_name
    else:
        joining, leaving = group2, group1
        join_team, counterpart_team = team_group2_name, team_group1_name

    player_variants = player_name_variants(tags)
    cash1, cash2 = _find_cash_mentions(raw_text, split_pos)
    group1_desc = [canonical_player_name(player_variants, t.int_id) for t in group1] + cash1
    group2_desc = [canonical_player_name(player_variants, t.int_id) for t in group2] + cash2
    joining_desc, leaving_desc = (group1_desc, group2_desc) if tracked_is_group1 else (group2_desc, group1_desc)

    joining_refs = [player_ref(canonical_player_name(player_variants, t.int_id), t.int_id) for t in joining]
    leaving_refs = [player_ref(canonical_player_name(player_variants, t.int_id), t.int_id) for t in leaving]

    description = build_trade_description(joining_desc, leaving_desc)
    form = ManualTransferFormData(
        achieved_date=achieved_date,
        joining_players=", ".join(joining_refs),
        leaving_players=", ".join(leaving_refs),
        event_type="trade",
        join_team=join_team,
        counterpart_team=counterpart_team,
        season=season,
        description=description,
        notes=notes or "",
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# FA contract / contract extension
# --------------------------------------------------------------------------

_YEARS_PATTERNS = [
    re.compile(r"(\d+)-year extension", re.I),
    re.compile(r"over\s+(?:the\s+)?(?:upcoming\s+)?(\d+)\s+years?", re.I),
    re.compile(r"next\s+(\d+)\s+years?", re.I),
    re.compile(r"for\s+(\d+)\s+years?", re.I),
]
_MONEY_PER_YEAR_RE = re.compile(r"\$([\d,]+)\s+(?:a year|per annum|per year)\b", re.I)
_MONEY_WORTH_RE = re.compile(r"worth\s+\$([\d,]+)", re.I)
_MONEY_SALARY_RE = re.compile(r"\$([\d,]+)\s+in salary\b", re.I)
_MONEY_OVER_RE = re.compile(r"\$([\d,]+)\s+over\b", re.I)
_MONEY_FALLBACK_RE = re.compile(r"\$([\d,]+)")


def _extract_contract_years(plain_text: str) -> int | None:
    for pattern in _YEARS_PATTERNS:
        m = pattern.search(plain_text)
        if m:
            return int(m.group(1))
    return None


def _extract_contract_total(plain_text: str, years: int | None) -> int | None:
    m = _MONEY_PER_YEAR_RE.search(plain_text)
    if m:
        per_year = int(m.group(1).replace(",", ""))
        return per_year * years if years else per_year
    for pattern in (_MONEY_WORTH_RE, _MONEY_SALARY_RE, _MONEY_OVER_RE, _MONEY_FALLBACK_RE):
        m = pattern.search(plain_text)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def extract_fa_or_extension(
    *,
    is_extension: bool,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
    notes: str | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    player_tags = [t for t in tags if t.kind == "player" and t.int_id is not None]
    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    if not player_tags or not team_tags:
        return ExtractResult([], "unparseable_contract_structure")

    player_variants = player_name_variants(tags)
    team_variants = team_name_variants(tags)

    player_tag = player_tags[0]
    player_name = canonical_player_name(player_variants, player_tag.int_id)

    team_tag = team_tags[0]
    team_name = canonical_team_name(team_variants, team_tag.int_id)
    team_name = preferred_tracked_team_name(team_name, tracked_teams)

    if not is_tracked_team_name(team_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    years = _extract_contract_years(plain_text)
    total = _extract_contract_total(plain_text, years)
    if years is None or total is None:
        return ExtractResult([], "unparseable_contract_terms")

    suffix = "연장 계약 체결" if is_extension else "FA 계약 체결"
    description = f"{years}년 ${total:,} {suffix}"

    form = ManualTransferFormData(
        achieved_date=achieved_date,
        joining_players=player_ref(player_name, player_tag.int_id),
        leaving_players="",
        event_type="extension_contract" if is_extension else "fa_contract",
        # Previous team is never named in these news bodies, so the
        # counterpart stays blank (field rules SS3/4: "상대팀: 알 수 있을 때만").
        join_team=team_name,
        counterpart_team="",
        season=season,
        description=description,
        notes=notes or "",
        fa_is_retention=None if is_extension else False,
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# Injury
# --------------------------------------------------------------------------

_INJURY_LABEL_TRIGGERS = [
    re.compile(r"including\s+(?:an?\s+)?([a-z][a-z '\-]*?)(?=,| during| while| and\b| on \d|\.|$)", re.I),
    re.compile(
        r"(?:suffered|sustained|diagnosed with|recovery from)\s+(?:an?\s+)?([a-z][a-z '\-]*?)"
        r"(?=,| during| while| and\b| on \d|\.|$)",
        re.I,
    ),
]
_DURATION_SEASON_OUT = re.compile(
    r"tommy john|shuts down|season is officially over|out for (?:the )?season|season-ending|\b\d+\s*-\s*\d+\s*months?\b",
    re.I,
)
_DURATION_ONE_WEEK = re.compile(r"\bone week\b", re.I)
_DURATION_WEEKS = re.compile(r"(\d+)\s*weeks?", re.I)
_DURATION_MONTHS = re.compile(r"(\d+)\s*months?", re.I)
_DURATION_FEW_DAYS = re.compile(r"a few days", re.I)
_DURATION_DAYS = re.compile(r"(\d+)\s*days?", re.I)


def _extract_injury_label(plain_text: str) -> str | None:
    for pattern in _INJURY_LABEL_TRIGGERS:
        m = pattern.search(plain_text)
        if m:
            label = m.group(1).strip()
            if label:
                return label
    return None


def _extract_injury_duration(plain_text: str) -> str:
    if _DURATION_SEASON_OUT.search(plain_text):
        return "시즌 아웃"
    if _DURATION_ONE_WEEK.search(plain_text):
        return "1주"
    m = _DURATION_WEEKS.search(plain_text)
    if m:
        return f"{m.group(1)}주"
    m = _DURATION_MONTHS.search(plain_text)
    if m:
        return f"{m.group(1)}개월"
    if _DURATION_FEW_DAYS.search(plain_text):
        return "며칠"
    m = _DURATION_DAYS.search(plain_text)
    if m:
        return f"{m.group(1)}일"
    return ""


def extract_injury(
    *,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
    notes: str | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    player_tags = [t for t in tags if t.kind == "player" and t.int_id is not None]
    if not player_tags:
        return ExtractResult([], "unparseable_injury_structure")
    player_variants = player_name_variants(tags)
    player_tag = player_tags[0]
    player_name = canonical_player_name(player_variants, player_tag.int_id)

    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    if team_tags:
        team_variants = team_name_variants(tags)
        team_name = canonical_team_name(team_variants, team_tags[0].int_id)
        team_name = preferred_tracked_team_name(team_name, tracked_teams)
    else:
        inferred = re.search(
            r"(?:\n|^)(?:The\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)"
            r"\s+(?:right fielder|left fielder|center fielder|equipment manager)",
            plain_text,
        )
        if not inferred:
            return ExtractResult([], "team_unresolved")
        team_name = inferred.group(1)

    if not is_tracked_team_name(team_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    injury_label = _extract_injury_label(plain_text)
    if not injury_label:
        return ExtractResult([], "unparseable_injury_terms")
    duration = _extract_injury_duration(plain_text)
    description = build_injury_description(injury_label, duration)

    form = ManualInjuryFormData(
        player_name=player_ref(player_name, player_tag.int_id),
        achieved_date=achieved_date,
        injury_label=injury_label,
        duration=duration,
        team=team_name,
        season=season,
        description=description,
        notes=notes or "",
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# Vote-table awards: MVP / Cy Young / Rookie of the Year
# --------------------------------------------------------------------------

_VOTE_ROW_RE = re.compile(r"<([^<>:]+):player#(\d+)>\s*-\s*<([^<>:]+):team#(\d+)>\s*-\s*(\d+)\s*-\s*(\d+)")

_VOTE_AWARD_KEYS: dict[str, tuple[str | None, str | None]] = {
    classify.CAT_AWARD_MVP: ("bat_season_award_mvp", "pit_season_award_mvp"),
    classify.CAT_AWARD_CY_YOUNG: (None, "pit_season_award_cy_young"),
    classify.CAT_AWARD_ROY: ("bat_season_award_rookie_of_year", "pit_season_award_rookie_of_year"),
}
_VOTE_AWARD_LABELS = {
    classify.CAT_AWARD_MVP: "MVP",
    classify.CAT_AWARD_CY_YOUNG: "사이영상",
    classify.CAT_AWARD_ROY: "신인왕",
}


@dataclass(frozen=True)
class _VoteRow:
    player_id: int
    player_name: str
    team_id: int
    team_name: str
    votes: int
    points: int


def _parse_vote_table(raw_text: str) -> list[_VoteRow]:
    return [
        _VoteRow(
            player_id=int(m.group(2)),
            player_name=m.group(1),
            team_id=int(m.group(4)),
            team_name=m.group(3),
            votes=int(m.group(5)),
            points=int(m.group(6)),
        )
        for m in _VOTE_ROW_RE.finditer(raw_text)
    ]


def _select_bat_or_pit_key(bat_key: str | None, pit_key: str | None, plain_text: str) -> str | None:
    is_pitcher = "ERA" in plain_text
    if is_pitcher and pit_key:
        return pit_key
    if not is_pitcher and bat_key:
        return bat_key
    return pit_key or bat_key


def extract_vote_award(
    *,
    category: str,
    raw_text: str,
    plain_text: str,
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    rows = _parse_vote_table(raw_text)
    if not rows:
        return ExtractResult([], "unparseable_vote_table")
    winner = rows[0]

    if not is_tracked_team_name(winner.team_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    bat_key, pit_key = _VOTE_AWARD_KEYS[category]
    milestone_key = _select_bat_or_pit_key(bat_key, pit_key, plain_text)
    if milestone_key is None:
        return ExtractResult([], "unparseable_award_key")

    award_label = _VOTE_AWARD_LABELS[category]
    if "unanimous" in plain_text.lower():
        description = f"{winner.votes}표 만장일치로 {award_label} 수상"
    else:
        description = f"{winner.votes}표 {winner.points} 포인트로 {award_label} 수상"

    note_parts = [
        f"{row.player_name} {row.votes}표 {row.points}포인트로 {rank}위"
        for rank, row in enumerate(rows[1:], start=2)
        if is_tracked_team_name(row.team_name, tracked_teams)
    ]

    form = ManualMilestoneFormData(
        target="player",
        achieved_date=achieved_date,
        player_id=winner.player_id,
        team=winner.team_name,
        milestone_key=milestone_key,
        season=season,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description=description,
        notes=", ".join(note_parts),
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# Position-list awards: Great Glove / Platinum Stick
# --------------------------------------------------------------------------

_POSITION_BLOCK_RE = re.compile(
    r"<([^<>:]+):value_bold#0>\s*\n<([^<>:]+):player#(\d+)>\s*\(<([^<>:]+):team#(\d+)>\)"
)
_POSITION_ABBR = {
    "Pitcher": "P",
    "Catcher": "C",
    "First Baseman": "1B",
    "Second Baseman": "2B",
    "Third Baseman": "3B",
    "Shortstop": "SS",
    "Left Fielder": "LF",
    "Center Fielder": "CF",
    "Right Fielder": "RF",
    "Designated Hitter": "DH",
}
_LEAGUE_NAME_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)*\sLeague)\b")


def _extract_league_name(text: str) -> str | None:
    for m in _LEAGUE_NAME_RE.finditer(text):
        if m.group(1).strip().lower() == "major league":
            continue
        return m.group(1)
    return None


def extract_position_list_award(
    *,
    category: str,
    raw_text: str,
    plain_text: str,
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    league = _extract_league_name(plain_text)
    if league is None:
        return ExtractResult([], "unparseable_award_league")

    is_platinum_stick = category == classify.CAT_AWARD_PLATINUM_STICK
    forms: list[Form] = []
    for m in _POSITION_BLOCK_RE.finditer(raw_text):
        position, player_name, player_id, team_name, _team_id = m.groups()
        if not is_tracked_team_name(team_name, tracked_teams):
            continue
        if is_platinum_stick:
            milestone_key = "bat_season_award_silver_slugger"
        else:
            milestone_key = "pit_season_award_gold_glove" if position == "Pitcher" else "bat_season_award_gold_glove"
        abbr = _POSITION_ABBR.get(position, position)
        forms.append(
            ManualMilestoneFormData(
                target="player",
                achieved_date=achieved_date,
                player_id=int(player_id),
                team=team_name,
                milestone_key=milestone_key,
                season=season,
                achieved_value=1.0,
                games_at_achievement=None,
                opponent_team="",
                opponent_player="",
                description=f"{league} {abbr}",
                notes="",
            )
        )
    if not forms:
        return ExtractResult([], "tracked_team_not_involved")
    return ExtractResult(forms)


# --------------------------------------------------------------------------
# Player of the month (batter / pitcher / rookie)
# --------------------------------------------------------------------------

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_KOREAN = {name: f"{i}월" for i, name in enumerate(_MONTH_NAMES, start=1)}
_MONTH_RE = re.compile(r"\b(" + "|".join(_MONTH_NAMES) + r")\b")


def _extract_month_korean(plain_text: str, message_date: date | None) -> str | None:
    m = _MONTH_RE.search(plain_text)
    if m:
        return _MONTH_KOREAN[m.group(1)]
    if message_date is not None:
        target_month = message_date.month - 1 or 12
        return f"{target_month}월"
    return None


def extract_player_of_month(
    *,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
    message_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    lower = plain_text.lower()
    if "rookie of the month" in lower:
        award_type = "신인"
    elif "pitcher of the month" in lower:
        award_type = "투수"
    elif "batter of the month" in lower:
        award_type = "타자"
    else:
        return ExtractResult([], "unparseable_award_type")

    player_tags = [t for t in tags if t.kind == "player" and t.int_id is not None]
    if not player_tags:
        return ExtractResult([], "unparseable_award_structure")
    player_id = player_tags[0].int_id

    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    if team_tags:
        team_variants = team_name_variants(tags)
        team_name = canonical_team_name(team_variants, team_tags[0].int_id)
        team_name = preferred_tracked_team_name(team_name, tracked_teams)
    else:
        inferred = re.search(r"^([A-Z][A-Za-z .'-]+)'s\s+", plain_text)
        if not inferred:
            return ExtractResult([], "team_unresolved")
        team_name = inferred.group(1).strip()

    if not is_tracked_team_name(team_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    month_label = _extract_month_korean(plain_text, message_date)
    if month_label is None:
        return ExtractResult([], "unparseable_award_month")

    if award_type == "투수":
        milestone_key = "pit_season_award_player_of_month"
    elif award_type == "타자":
        milestone_key = "bat_season_award_player_of_month"
    else:
        milestone_key = "pit_season_award_player_of_month" if "ERA" in plain_text else "bat_season_award_player_of_month"

    form = ManualMilestoneFormData(
        target="player",
        achieved_date=achieved_date,
        player_id=player_id,
        team=team_name,
        milestone_key=milestone_key,
        season=season,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description=f"이달의 {award_type} ({month_label}) 수상",
        notes="",
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# All-Star roster
# --------------------------------------------------------------------------

_ALL_STAR_LINE_RE = re.compile(
    r"^(SP|RP|CL|C|1B|2B|3B|SS|LF|CF|RF|DH)\s+<([^<>:]+):player#(\d+)>\s*\(([A-Za-z]{2,4})\)",
    re.MULTILINE,
)
_ALL_STAR_PITCHING_POSITIONS = {"SP", "RP", "CL"}


def _extract_league_token(title: str) -> str:
    m = re.match(r"^([A-Za-z]+)\s+(?:Headline News|News)\b", title.strip())
    return m.group(1) if m else "MLB"


def _match_tracked_team_for_abbr(abbr: str, tracked_teams: list[str]) -> str | None:
    abbr_upper = abbr.strip().upper()
    if not tracked_teams:
        return abbr_upper
    for tracked in tracked_teams:
        if abbr_upper in team_abbreviation_candidates(tracked):
            return tracked
    return None


def extract_all_star(
    *,
    title: str,
    raw_text: str,
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")

    description = f"{_extract_league_token(title)} 선발"

    forms: list[Form] = []
    for m in _ALL_STAR_LINE_RE.finditer(raw_text):
        position, _player_name, player_id, abbr = m.groups()
        matched_team = _match_tracked_team_for_abbr(abbr, tracked_teams)
        if matched_team is None:
            continue
        milestone_key = (
            "pit_season_award_all_star"
            if position in _ALL_STAR_PITCHING_POSITIONS
            else "bat_season_award_all_star"
        )
        forms.append(
            ManualMilestoneFormData(
                target="player",
                achieved_date=achieved_date,
                player_id=int(player_id),
                team=matched_team,
                milestone_key=milestone_key,
                season=season,
                achieved_value=1.0,
                games_at_achievement=None,
                opponent_team="",
                opponent_player="",
                description=description,
                notes="",
            )
        )
    if not forms:
        return ExtractResult([], "tracked_team_not_involved")
    return ExtractResult(forms)


# --------------------------------------------------------------------------
# Postseason: division title / World Series
# --------------------------------------------------------------------------

_DIVISION_RE = re.compile(r"(American League|National League)\s+(West|East|Central)\s+Division", re.I)
_LEAGUE_SHORT = {"american league": "AL", "national league": "NL"}


def extract_division(
    *,
    title: str,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")
    if season is None:
        return ExtractResult([], "season_unknown")

    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    if not team_tags:
        return ExtractResult([], "unparseable_postseason_structure")
    team_variants = team_name_variants(tags)
    winner_name = canonical_team_name(team_variants, team_tags[0].int_id)
    winner_name = preferred_tracked_team_name(winner_name, tracked_teams)

    if not is_tracked_team_name(winner_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    m = _DIVISION_RE.search(f"{title}\n{plain_text}")
    if not m:
        return ExtractResult([], "unparseable_division_name")
    league_short = _LEAGUE_SHORT[m.group(1).lower()]
    description = f"{league_short} {m.group(2)} {season}"

    form = ManualMilestoneFormData(
        target="team",
        achieved_date=achieved_date,
        player_id=None,
        team=winner_name,
        milestone_key="team_season_division_title",
        season=season,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description=description,
        notes="",
    )
    return ExtractResult([form])


def extract_world_series(
    *,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")
    if season is None:
        return ExtractResult([], "season_unknown")

    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    distinct_ids: list[int] = []
    for t in team_tags:
        if t.int_id not in distinct_ids:
            distinct_ids.append(t.int_id)
    if len(distinct_ids) < 2:
        return ExtractResult([], "unparseable_postseason_structure")

    team_variants = team_name_variants(tags)
    winner_name = canonical_team_name(team_variants, distinct_ids[0])
    loser_name = canonical_team_name(team_variants, distinct_ids[1])
    winner_name = preferred_tracked_team_name(winner_name, tracked_teams)
    loser_name = preferred_tracked_team_name(loser_name, tracked_teams)

    if not is_tracked_team_name(winner_name, tracked_teams):
        return ExtractResult([], "tracked_team_not_involved")

    score_match = re.search(r"swept.{0,60}?(\d+)-(\d+)", plain_text, re.I | re.S)
    if score_match:
        description = f"{season} {score_match.group(1)}-{score_match.group(2)} 스윕"
    else:
        generic_score = re.search(r"\b(\d+)-(\d+)\b", plain_text)
        description = f"{season} {generic_score.group(0)}" if generic_score else f"{season} 우승"

    form = ManualMilestoneFormData(
        target="team",
        achieved_date=achieved_date,
        player_id=None,
        team=winner_name,
        milestone_key="team_season_world_series_win",
        season=season,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team=loser_name,
        opponent_player="",
        description=description,
        notes="",
    )
    return ExtractResult([form])


# --------------------------------------------------------------------------
# Hall of Fame
# --------------------------------------------------------------------------


def extract_hall_of_fame(
    *,
    plain_text: str,
    tags: list[MessageTag],
    tracked_teams: list[str],
    season: int | None,
    achieved_date: date | None,
) -> ExtractResult:
    if achieved_date is None:
        return ExtractResult([], "message_date_required")
    if season is None:
        return ExtractResult([], "season_unknown")

    player_tags = [t for t in tags if t.kind == "player" and t.int_id is not None]
    if not player_tags:
        return ExtractResult([], "unparseable_hof_structure")
    player_variants = player_name_variants(tags)
    player_id = player_tags[0].int_id
    _ = canonical_player_name(player_variants, player_id)

    team_tags = [t for t in tags if t.kind == "team" and t.int_id is not None]
    team_name = ""
    if team_tags:
        team_variants = team_name_variants(tags)
        candidate = canonical_team_name(team_variants, team_tags[0].int_id)
        # Only exclude on a *resolvable but non-tracked* team; when the
        # message names no team at all we still record (README lists
        # hall_of_fame_01 -- team-less -- as an in-scope automation sample).
        if not is_tracked_team_name(candidate, tracked_teams):
            return ExtractResult([], "tracked_team_not_involved")
        team_name = candidate

    league = _extract_league_name(plain_text)
    is_pitcher = "ERA" in plain_text
    milestone_key = "pit_career_hall_of_fame" if is_pitcher else "bat_career_hall_of_fame"
    description = f"{league} 헌액" if league else "명예의 전당 헌액"

    form = ManualMilestoneFormData(
        target="player",
        achieved_date=achieved_date,
        player_id=player_id,
        team=team_name,
        milestone_key=milestone_key,
        season=season,
        achieved_value=1.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description=description,
        notes="",
    )
    return ExtractResult([form])
