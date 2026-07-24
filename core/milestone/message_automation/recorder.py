"""Route a `ParsedMessage` into the existing manual-entry persistence path.

This module performs no INSERT itself -- each form is dispatched to the
matching `MilestoneChecker.record_manual_*` method, exactly as the manual
entry GUI dialogs already do (field rules S12), so duplicate-detection,
player registration, and schema details stay in one place.
"""

from __future__ import annotations

import re
from typing import Any

from core.milestone.checker import MilestoneChecker
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
)

from .parser import ParsedMessage

_PLAYER_REF_RE = re.compile(r"([^,]+?)\s*\(#(\d+)\)")


def record_parsed_message(checker: MilestoneChecker, parsed: ParsedMessage) -> list[int]:
    """Persist every form in `parsed` via the existing manual-entry path.

    Returns the new `milestone_records` row ids (empty for an excluded
    message -- check `parsed.excluded` / `parsed.exclusion_reason` first if
    the caller wants to report why nothing was recorded).
    """
    if parsed.excluded:
        return []

    ids: list[int] = []
    for form in parsed.forms:
        _seed_form_players(checker.aggregator.conn, form, parsed.player_names)
        if _form_already_recorded(checker.aggregator.conn, form):
            continue
        if isinstance(form, ManualTransferFormData):
            ids.extend(checker.record_manual_transfer(form))
        elif isinstance(form, ManualInjuryFormData):
            ids.append(checker.record_manual_injury(form))
        elif isinstance(form, ManualMilestoneFormData):
            ids.append(checker.record_manual_milestone(form))
        else:
            raise TypeError(f"Unsupported form type: {type(form)!r}")
    return ids


def apply_parsed_messages(
    parsed_messages: ParsedMessage | list[ParsedMessage],
    *,
    checker: MilestoneChecker,
    aggregator: Any | None = None,
) -> list[dict[str, Any]]:
    """Compatibility/batch API returning the rows created by this call."""

    del aggregator
    messages = (
        [parsed_messages]
        if isinstance(parsed_messages, ParsedMessage)
        else list(parsed_messages)
    )
    conn = checker.aggregator.conn
    created_ids: list[int] = []
    for parsed in messages:
        created_ids.extend(record_parsed_message(checker, parsed))
    rows: list[dict[str, Any]] = []
    for record_id in created_ids:
        row = conn.execute(
            "SELECT * FROM milestone_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row is not None:
            rows.append(dict(row))
    return rows


def _seed_form_players(
    conn: Any, form: object, player_names: dict[int, str]
) -> None:
    refs: list[tuple[str, int]] = []
    if isinstance(form, ManualTransferFormData):
        refs.extend(_player_refs(form.joining_players))
        refs.extend(_player_refs(form.leaving_players))
    elif isinstance(form, ManualInjuryFormData):
        refs.extend(_player_refs(form.player_name))
    elif (
        isinstance(form, ManualMilestoneFormData)
        and form.target == "player"
        and form.player_id
        and form.player_id in player_names
    ):
        refs.append((player_names[form.player_id], int(form.player_id)))
    for name, player_id in refs:
        if conn.execute(
            "SELECT 1 FROM players WHERE player_id = ?", (player_id,)
        ).fetchone():
            continue
        from core.roster.player_registry import derive_short_name

        conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (?, ?, ?)
            """,
            (player_id, name, derive_short_name(name)),
        )


def _player_refs(text: str) -> list[tuple[str, int]]:
    return [
        (match.group(1).strip(), int(match.group(2)))
        for match in _PLAYER_REF_RE.finditer(text)
    ]


def _form_already_recorded(conn: Any, form: object) -> bool:
    notes = str(getattr(form, "notes", "") or "")
    if not notes:
        return False
    if isinstance(form, ManualTransferFormData):
        key = f"manual_transfer_{form.event_type}"
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE milestone_key = ? AND season IS ? AND notes = ?
            LIMIT 1
            """,
            (key, form.season, notes),
        ).fetchone()
        return row is not None
    if isinstance(form, ManualInjuryFormData):
        refs = _player_refs(form.player_name)
        player_id = refs[0][1] if refs else None
        row = conn.execute(
            """
            SELECT 1 FROM milestone_records
            WHERE milestone_key = 'manual_injury' AND player_id IS ?
              AND season IS ? AND notes = ?
            LIMIT 1
            """,
            (player_id, form.season, notes),
        ).fetchone()
        return row is not None
    if isinstance(form, ManualMilestoneFormData):
        if form.target == "team":
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE milestone_key = ? AND team IS ? AND season IS ?
                  AND notes = ?
                LIMIT 1
                """,
                (form.milestone_key, form.team, form.season, notes),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1 FROM milestone_records
                WHERE milestone_key = ? AND player_id IS ? AND season IS ?
                  AND notes = ?
                LIMIT 1
                """,
                (form.milestone_key, form.player_id, form.season, notes),
            ).fetchone()
        return row is not None
    return False
