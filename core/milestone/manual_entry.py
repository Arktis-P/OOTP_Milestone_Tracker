"""Manual milestone entry validation and helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from core.i18n import tr
from core.milestone.definitions import MilestoneDefinition

TargetKind = Literal["player", "team"]
DuplicateKind = Literal["none", "warn", "exists"]
ManualEntryCategory = Literal["milestone", "award"]


@dataclass
class ManualMilestoneFormData:
    target: TargetKind
    achieved_date: date
    player_id: int | None
    team: str | None
    milestone_key: str
    season: int | None
    achieved_value: float
    games_at_achievement: int | None
    opponent_team: str
    opponent_player: str
    description: str
    notes: str


@dataclass
class ManualTransferFormData:
    achieved_date: date
    joining_players: str
    leaving_players: str
    event_type: str
    join_team: str
    counterpart_team: str
    season: int | None
    description: str
    notes: str


@dataclass
class ManualInjuryFormData:
    player_name: str
    achieved_date: date
    injury_label: str
    duration: str
    team: str
    season: int | None
    description: str
    notes: str


@dataclass
class TransferPlayerRecord:
    player_id: int
    label: str
    team: str | None
    opponent_team: str | None
    description: str


TRANSFER_EVENT_LABELS: dict[str, str] = {
    "fa_contract": "FA Contract",
    "extension_contract": "Extension Contract",
    "trade": "Trade",
    "player_purchase": "Player Purchase",
}


def parse_flexible_date(text: str) -> date | None:
    """Parse flexible date strings (YY/YYYY + separators or compact digits)."""
    raw = text.strip()
    if not raw:
        return None

    if re.fullmatch(r"\d{6}", raw):
        yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
        return _safe_date(2000 + yy, mm, dd)

    if re.fullmatch(r"\d{8}", raw):
        yyyy, mm, dd = int(raw[0:4]), int(raw[4:6]), int(raw[6:8])
        return _safe_date(yyyy, mm, dd)

    for sep in ("-", "/"):
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) != 3:
                return None
            try:
                y, m, d = (int(p) for p in parts)
            except ValueError:
                return None
            if y < 100:
                y += 2000
            return _safe_date(y, m, d)

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def get_achieved_value_candidates(milestone: MilestoneDefinition) -> list[str]:
    threshold = int(milestone.threshold)
    if milestone.direction == "lower":
        return [str(threshold - offset) for offset in range(0, 4)]
    return [str(threshold + offset) for offset in range(0, 4)]


def scope_needs_season(scope: str) -> bool:
    return scope in ("season", "season_ratio", "team_season", "team_manual")


def scope_needs_games_at_achievement(scope: str) -> bool:
    return scope in ("season", "career", "team_season")


def milestones_for_target(
    milestones: list[MilestoneDefinition],
    target: TargetKind,
) -> list[MilestoneDefinition]:
    if target == "team":
        return [m for m in milestones if m.category == "team" and m.active]
    return [m for m in milestones if m.category != "team" and m.active]


def milestones_for_manual_entry(
    milestones: list[MilestoneDefinition],
    target: TargetKind,
    *,
    category: ManualEntryCategory,
) -> list[MilestoneDefinition]:
    from core.milestone.implementation import is_award_milestone

    pool = milestones_for_target(milestones, target)
    if category == "award":
        return [m for m in pool if is_award_milestone(m)]
    return [m for m in pool if not is_award_milestone(m)]


def validate_manual_entry(
    form: ManualMilestoneFormData,
    milestone: MilestoneDefinition | None,
) -> list[str]:
    errors: list[str] = []
    if milestone is None:
        errors.append(tr("Please select a milestone."))
        return errors

    if form.target == "player" and not form.player_id:
        errors.append(tr("Please select a player."))
    if form.target == "team" and not (form.team or "").strip():
        errors.append(tr("Please select a team."))

    scope = milestone.scope
    if scope_needs_season(scope) and form.season is None:
        errors.append(tr("Please enter a season."))
    if scope_needs_games_at_achievement(scope) and form.games_at_achievement is None:
        errors.append(tr("Please enter games at achievement."))

    return errors


def validate_manual_transfer(form: ManualTransferFormData) -> list[str]:
    errors: list[str] = []
    if form.event_type not in TRANSFER_EVENT_LABELS:
        errors.append(tr("Please select a transfer type."))
    joining = parse_player_name_list(form.joining_players)
    leaving = parse_player_name_list(form.leaving_players)
    if not joining and not leaving:
        errors.append(tr("Please enter joining or leaving players."))
    if not form.join_team.strip():
        errors.append(tr("Please enter the joining team."))
    return errors


def validate_manual_injury(form: ManualInjuryFormData) -> list[str]:
    errors: list[str] = []
    if not parse_player_name_list(form.player_name):
        errors.append(tr("Please enter a player."))
    if not form.injury_label.strip():
        errors.append(tr("Please enter the injury."))
    if not form.team.strip():
        errors.append(tr("Please enter the affiliated team."))
    return errors


def parse_player_name_list(text: str) -> list[str]:
    names: list[str] = []
    for part in text.split(","):
        raw = part.strip()
        if not raw:
            continue
        raw = re.sub(r"^\[[^\]]+\]\s*", "", raw).strip()
        raw = re.sub(r"^\[수동\]\s*", "", raw).strip()
        raw = re.sub(r"\s*\(#\d+\)\s*$", "", raw).strip()
        if raw:
            names.append(raw)
    return names


def resolve_player_id(conn: Any, name: str) -> int | None:
    id_match = re.search(r"\(#(\d+)\)\s*$", name.strip())
    if id_match:
        return int(id_match.group(1))

    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", name.strip())
    cleaned = re.sub(r"^\[수동\]\s*", "", cleaned).strip()
    cleaned = re.sub(r"\s*\(#\d+\)\s*$", "", cleaned).strip()
    if not cleaned:
        return None

    row = conn.execute(
        """
        SELECT player_id FROM players
        WHERE short_name = ? OR full_name = ?
        LIMIT 1
        """,
        (cleaned, cleaned),
    ).fetchone()
    if row:
        return int(row["player_id"])

    from core.roster.player_registry import derive_short_name, normalize_player_name

    probe = normalize_player_name(cleaned)
    derived = normalize_player_name(derive_short_name(cleaned))
    rows = conn.execute(
        """
        SELECT player_id, full_name, short_name FROM players
        """
    ).fetchall()
    for row in rows:
        keys = {
            normalize_player_name(str(row["full_name"] or "")),
            normalize_player_name(str(row["short_name"] or "")),
            normalize_player_name(derive_short_name(str(row["full_name"] or ""))),
        }
        keys.discard("")
        if probe in keys or derived in keys:
            return int(row["player_id"])

    row = conn.execute(
        """
        SELECT player_id FROM players
        WHERE short_name LIKE ? OR full_name LIKE ?
        LIMIT 1
        """,
        (cleaned, cleaned),
    ).fetchone()
    return int(row["player_id"]) if row else None


def resolve_transfer_players(
    conn: Any, names: list[str], *, registry: Any | None = None
) -> tuple[list[int], list[str]]:
    ids: list[int] = []
    errors: list[str] = []
    for name in names:
        if registry is not None:
            try:
                ids.append(int(registry.ensure_player(name)))
            except ValueError as exc:
                errors.append(str(exc))
            continue
        player_id = resolve_player_id(conn, name)
        if player_id is None:
            errors.append(tr("Player not found: {name}").format(name=name))
        else:
            ids.append(player_id)
    return ids, errors


def build_trade_description(joining: list[str], leaving: list[str]) -> str:
    left = ", ".join(joining)
    right = ", ".join(leaving)
    if left and right:
        return f"{left} <> {right} 트레이드"
    if left:
        return f"{left} 트레이드"
    if right:
        return f"{right} 트레이드"
    return ""


def _josa_ro(word: str) -> str:
    text = word.strip()
    if not text:
        return "으로"
    last = text[-1]
    if "가" <= last <= "힣":
        if (ord(last) - 0xAC00) % 28 == 0:
            return "로"
    return "으로"


def build_injury_description(injury_label: str, duration: str) -> str:
    label = injury_label.strip()
    josa = _josa_ro(label)
    period = duration.strip()
    if period:
        return f"{label}{josa} {period} 진단"
    return f"{label}{josa} 결장"


def build_transfer_records(
    conn: Any,
    form: ManualTransferFormData,
    *,
    registry: Any | None = None,
) -> tuple[list[TransferPlayerRecord], list[str]]:
    joining_names = parse_player_name_list(form.joining_players)
    leaving_names = parse_player_name_list(form.leaving_players)
    join_team = form.join_team.strip()
    counterpart = form.counterpart_team.strip()
    description = form.description.strip()
    errors: list[str] = []

    joining_ids, join_errors = resolve_transfer_players(
        conn, joining_names, registry=registry
    )
    leaving_ids, leave_errors = resolve_transfer_players(
        conn, leaving_names, registry=registry
    )
    errors.extend(join_errors)
    errors.extend(leave_errors)
    if errors:
        return [], errors

    records: list[TransferPlayerRecord] = []
    event_type = form.event_type

    if event_type == "trade":
        for player_id in joining_ids:
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label="트레이드로 합류",
                    team=join_team or None,
                    opponent_team=counterpart or None,
                    description=description,
                )
            )
        for player_id in leaving_ids:
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label="트레이드로 이탈",
                    team=counterpart or None,
                    opponent_team=join_team or None,
                    description=description,
                )
            )
        return records, []

    if event_type == "extension_contract":
        for player_id in joining_ids + leaving_ids:
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label="연장 계약 잔류",
                    team=join_team or None,
                    opponent_team=None,
                    description=description,
                )
            )
        return records, []

    if event_type == "fa_contract":
        has_counterpart = bool(counterpart)
        for player_id in joining_ids:
            label = (
                "FA 계약 잔류"
                if not has_counterpart
                else "FA 계약 합류"
            )
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label=label,
                    team=join_team or None,
                    opponent_team=counterpart or None,
                    description=description,
                )
            )
        for player_id in leaving_ids:
            label = (
                "FA 계약 잔류"
                if not has_counterpart
                else "FA 계약 이탈"
            )
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label=label,
                    team=join_team or None,
                    opponent_team=counterpart or None,
                    description=description,
                )
            )
        return records, []

    if event_type == "player_purchase":
        for player_id in joining_ids:
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label="선수 구매 합류",
                    team=join_team or None,
                    opponent_team=counterpart or None,
                    description=description,
                )
            )
        for player_id in leaving_ids:
            records.append(
                TransferPlayerRecord(
                    player_id=player_id,
                    label="선수 구매 이탈",
                    team=join_team or None,
                    opponent_team=counterpart or None,
                    description=description,
                )
            )
        return records, []

    return [], [tr("Unsupported transfer type.")]


def check_duplicate(
    conn: Any,
    form: ManualMilestoneFormData,
    milestone: MilestoneDefinition,
) -> tuple[DuplicateKind, str]:
    scope = milestone.scope
    achieved_date = form.achieved_date.isoformat()

    if scope == "career" and form.target == "player":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE player_id = ? AND milestone_key = ? AND scope = 'career'
            """,
            (form.player_id, milestone.key),
        ).fetchone()
        if row:
            return "warn", tr("Already recorded career milestone.")

    if scope in ("season", "season_ratio") and form.target == "player":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE player_id = ? AND milestone_key = ? AND season = ?
            """,
            (form.player_id, milestone.key, form.season),
        ).fetchone()
        if row:
            return "warn", tr("Already recorded for this season.")

    if scope in ("team_season", "team_manual") and form.target == "team":
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE team = ? AND milestone_key = ? AND season = ?
            """,
            (form.team, milestone.key, form.season),
        ).fetchone()
        if row:
            return "warn", tr("Already recorded team milestone for this season.")

    if scope in ("game", "team_game"):
        if form.target == "player":
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE player_id = ? AND milestone_key = ? AND achieved_date = ?
                """,
                (form.player_id, milestone.key, achieved_date),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE team = ? AND milestone_key = ? AND achieved_date = ?
                """,
                (form.team, milestone.key, achieved_date),
            ).fetchone()
        if row:
            return "warn", tr("Already recorded on the same date.")

    return "none", ""
