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
from .processed import (
    MessageApplyResult,
    MessageSourceFingerprint,
    fingerprint_message_text,
    upsert_processed_message,
)

_PLAYER_REF_RE = re.compile(r"([^,]+?)\s*\(#(\d+)\)")


def record_parsed_message(checker: MilestoneChecker, parsed: ParsedMessage) -> list[int]:
    """Persist every form in `parsed` via the existing manual-entry path.

    Returns the new `milestone_records` row ids (empty for an excluded
    message -- check `parsed.excluded` / `parsed.exclusion_reason` first if
    the caller wants to report why nothing was recorded).
    """
    return record_parsed_message_result(checker, parsed).created_record_ids


def record_parsed_message_result(
    checker: MilestoneChecker,
    parsed: ParsedMessage,
    *,
    fingerprint: MessageSourceFingerprint | None = None,
) -> MessageApplyResult:
    """Persist one parsed message and return per-message created/duplicate ids."""

    source_id = parsed.source_id or ""
    if fingerprint is None:
        fingerprint = fingerprint_message_text("", source_id=source_id)
    if parsed.excluded:
        upsert_processed_message(
            checker.aggregator.conn,
            fingerprint=fingerprint,
            status="excluded",
            category=parsed.category,
            exclusion_reason=parsed.exclusion_reason,
        )
        return MessageApplyResult(source_id=source_id)

    created_ids: list[int] = []
    duplicate_ids: list[int] = []
    errors: list[str] = []
    for form in parsed.forms:
        try:
            _seed_form_players(checker.aggregator.conn, form, parsed.player_names)
        except Exception as exc:  # pragma: no cover - defensive reporting path
            errors.append(str(exc))
            continue
        existing = _form_existing_record_ids(checker.aggregator.conn, form)
        if existing:
            duplicate_ids.extend(existing)
            continue
        try:
            if isinstance(form, ManualTransferFormData):
                created_ids.extend(checker.record_manual_transfer(form, source="message_auto"))
            elif isinstance(form, ManualInjuryFormData):
                created_ids.append(checker.record_manual_injury(form, source="message_auto"))
            elif isinstance(form, ManualMilestoneFormData):
                created_ids.append(checker.record_manual_milestone(form, source="message_auto"))
            else:
                raise TypeError(f"Unsupported form type: {type(form)!r}")
        except Exception as exc:  # pragma: no cover - defensive reporting path
            errors.append(str(exc))
    result = MessageApplyResult(
        source_id=source_id,
        created_record_ids=created_ids,
        duplicate_record_ids=duplicate_ids,
        errors=errors,
    )
    upsert_processed_message(
        checker.aggregator.conn,
        fingerprint=fingerprint,
        status=result.status,
        category=parsed.category,
        exclusion_reason=parsed.exclusion_reason,
        created_record_ids=result.created_record_ids,
        duplicate_record_ids=result.duplicate_record_ids,
        errors=result.errors,
        mark_applied=bool(result.created_record_ids or result.duplicate_record_ids),
    )
    return result


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
        created_ids.extend(record_parsed_message_result(checker, parsed).created_record_ids)
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


def _form_existing_record_ids(conn: Any, form: object) -> list[int]:
    notes = str(getattr(form, "notes", "") or "")
    if not notes:
        return []
    if isinstance(form, ManualTransferFormData):
        key = f"manual_transfer_{form.event_type}"
        rows = conn.execute(
            """
            SELECT id FROM milestone_records
            WHERE milestone_key = ? AND season IS ? AND notes = ?
            """,
            (key, form.season, notes),
        ).fetchall()
        return [int(row["id"] if hasattr(row, "keys") else row[0]) for row in rows]
    if isinstance(form, ManualInjuryFormData):
        refs = _player_refs(form.player_name)
        player_id = refs[0][1] if refs else None
        rows = conn.execute(
            """
            SELECT id FROM milestone_records
            WHERE milestone_key = 'manual_injury' AND player_id IS ?
              AND season IS ? AND notes = ?
            """,
            (player_id, form.season, notes),
        ).fetchall()
        return [int(row["id"] if hasattr(row, "keys") else row[0]) for row in rows]
    if isinstance(form, ManualMilestoneFormData):
        if form.target == "team":
            rows = conn.execute(
                """
                SELECT id FROM milestone_records
                WHERE milestone_key = ? AND team IS ? AND season IS ?
                  AND notes = ?
                """,
                (form.milestone_key, form.team, form.season, notes),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id FROM milestone_records
                WHERE milestone_key = ? AND player_id IS ? AND season IS ?
                  AND notes = ?
                """,
                (form.milestone_key, form.player_id, form.season, notes),
            ).fetchall()
        return [int(row["id"] if hasattr(row, "keys") else row[0]) for row in rows]
    return []


def _form_already_recorded(conn: Any, form: object) -> bool:
    return bool(_form_existing_record_ids(conn, form))
