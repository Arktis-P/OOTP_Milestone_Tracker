"""Processed OOTP message storage and per-message application results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MessageSourceFingerprint:
    source_id: str
    source_path: str
    source_hash: str
    source_mtime: float


@dataclass(frozen=True)
class ProcessedMessage:
    source_id: str
    source_path: str = ""
    source_hash: str = ""
    source_mtime: float = 0.0
    status: str = "candidate"
    category: str = ""
    exclusion_reason: str | None = None
    created_record_ids: list[int] = field(default_factory=list)
    duplicate_record_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    parsed_at: str | None = None
    applied_at: str | None = None
    last_seen_at: str | None = None

    @property
    def is_already_applied(self) -> bool:
        return bool(self.created_record_ids or self.duplicate_record_ids) and self.status in {
            "applied",
            "duplicate",
        }

    def has_source_changed(self, fingerprint: MessageSourceFingerprint) -> bool:
        if self.source_hash and fingerprint.source_hash:
            return self.source_hash != fingerprint.source_hash
        if self.source_mtime and fingerprint.source_mtime:
            return self.source_mtime != fingerprint.source_mtime
        return False


@dataclass(frozen=True)
class MessageApplyResult:
    source_id: str
    created_record_ids: list[int] = field(default_factory=list)
    duplicate_record_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def saved_record_ids(self) -> list[int]:
        return list(self.created_record_ids)

    @property
    def is_success(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.created_record_ids:
            return "applied"
        if self.duplicate_record_ids:
            return "duplicate"
        return "skipped"


def ensure_processed_messages_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_messages (
            source_id            TEXT PRIMARY KEY,
            source_path          TEXT NOT NULL DEFAULT '',
            source_hash          TEXT NOT NULL DEFAULT '',
            source_mtime         REAL NOT NULL DEFAULT 0.0,
            status               TEXT NOT NULL DEFAULT 'candidate',
            category             TEXT NOT NULL DEFAULT '',
            exclusion_reason     TEXT,
            created_record_ids   TEXT NOT NULL DEFAULT '[]',
            duplicate_record_ids TEXT NOT NULL DEFAULT '[]',
            errors               TEXT NOT NULL DEFAULT '[]',
            parsed_at            TEXT DEFAULT (datetime('now')),
            applied_at           TEXT,
            last_seen_at         TEXT DEFAULT (datetime('now')),
            updated_at           TEXT DEFAULT (datetime('now'))
        )
        """
    )
    existing = {
        str(row["name"] if hasattr(row, "keys") else row[1])
        for row in conn.execute("PRAGMA table_info(processed_messages)").fetchall()
    }
    migrations = {
        "source_path": "ALTER TABLE processed_messages ADD COLUMN source_path TEXT NOT NULL DEFAULT ''",
        "source_hash": "ALTER TABLE processed_messages ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''",
        "source_mtime": "ALTER TABLE processed_messages ADD COLUMN source_mtime REAL NOT NULL DEFAULT 0.0",
        "status": "ALTER TABLE processed_messages ADD COLUMN status TEXT NOT NULL DEFAULT 'candidate'",
        "category": "ALTER TABLE processed_messages ADD COLUMN category TEXT NOT NULL DEFAULT ''",
        "exclusion_reason": "ALTER TABLE processed_messages ADD COLUMN exclusion_reason TEXT",
        "created_record_ids": "ALTER TABLE processed_messages ADD COLUMN created_record_ids TEXT NOT NULL DEFAULT '[]'",
        "duplicate_record_ids": "ALTER TABLE processed_messages ADD COLUMN duplicate_record_ids TEXT NOT NULL DEFAULT '[]'",
        "errors": "ALTER TABLE processed_messages ADD COLUMN errors TEXT NOT NULL DEFAULT '[]'",
        "parsed_at": "ALTER TABLE processed_messages ADD COLUMN parsed_at TEXT",
        "applied_at": "ALTER TABLE processed_messages ADD COLUMN applied_at TEXT",
        "last_seen_at": "ALTER TABLE processed_messages ADD COLUMN last_seen_at TEXT",
        "updated_at": "ALTER TABLE processed_messages ADD COLUMN updated_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def fingerprint_message_file(path: str | Path) -> MessageSourceFingerprint:
    message_path = Path(path)
    raw = message_path.read_bytes()
    return MessageSourceFingerprint(
        source_id=message_path.stem,
        source_path=str(message_path),
        source_hash=hashlib.sha256(raw).hexdigest(),
        source_mtime=message_path.stat().st_mtime,
    )


def fingerprint_message_text(
    text: str,
    *,
    source_id: str | None = None,
    source_path: str = "",
    source_mtime: float = 0.0,
) -> MessageSourceFingerprint:
    return MessageSourceFingerprint(
        source_id=source_id or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        source_path=source_path,
        source_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_mtime=float(source_mtime or 0.0),
    )


def get_processed_message(conn: Any, source_id: str) -> ProcessedMessage | None:
    ensure_processed_messages_schema(conn)
    row = conn.execute(
        """
        SELECT source_id, source_path, source_hash, source_mtime, status,
               category, exclusion_reason, created_record_ids,
               duplicate_record_ids, errors, parsed_at, applied_at, last_seen_at
        FROM processed_messages
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    data = dict(row) if hasattr(row, "keys") else {
        "source_id": row[0],
        "source_path": row[1],
        "source_hash": row[2],
        "source_mtime": row[3],
        "status": row[4],
        "category": row[5],
        "exclusion_reason": row[6],
        "created_record_ids": row[7],
        "duplicate_record_ids": row[8],
        "errors": row[9],
        "parsed_at": row[10],
        "applied_at": row[11],
        "last_seen_at": row[12],
    }
    return ProcessedMessage(
        source_id=data["source_id"],
        source_path=data["source_path"] or "",
        source_hash=data["source_hash"] or "",
        source_mtime=float(data["source_mtime"] or 0.0),
        status=data["status"] or "candidate",
        category=data["category"] or "",
        exclusion_reason=data["exclusion_reason"],
        created_record_ids=_decode_int_list(data["created_record_ids"]),
        duplicate_record_ids=_decode_int_list(data["duplicate_record_ids"]),
        errors=_decode_str_list(data["errors"]),
        parsed_at=data["parsed_at"],
        applied_at=data["applied_at"],
        last_seen_at=data["last_seen_at"],
    )


def get_message_rescan_status(
    conn: Any, fingerprint: MessageSourceFingerprint
) -> str:
    processed = get_processed_message(conn, fingerprint.source_id)
    if processed is None:
        return "new"
    if processed.has_source_changed(fingerprint):
        return "changed_review_needed"
    if processed.is_already_applied or processed.duplicate_record_ids:
        return "already_applied"
    return processed.status


def upsert_processed_message(
    conn: Any,
    *,
    fingerprint: MessageSourceFingerprint,
    status: str,
    category: str = "",
    exclusion_reason: str | None = None,
    created_record_ids: list[int] | None = None,
    duplicate_record_ids: list[int] | None = None,
    errors: list[str] | None = None,
    mark_applied: bool = False,
    commit: bool = True,
) -> ProcessedMessage:
    ensure_processed_messages_schema(conn)
    conn.execute(
        """
        INSERT INTO processed_messages (
            source_id, source_path, source_hash, source_mtime, status,
            category, exclusion_reason, created_record_ids,
            duplicate_record_ids, errors, parsed_at, applied_at, last_seen_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                  CASE WHEN ? THEN datetime('now') ELSE NULL END,
                  datetime('now'), datetime('now'))
        ON CONFLICT(source_id) DO UPDATE SET
            source_path = excluded.source_path,
            source_hash = excluded.source_hash,
            source_mtime = excluded.source_mtime,
            status = excluded.status,
            category = excluded.category,
            exclusion_reason = excluded.exclusion_reason,
            created_record_ids = excluded.created_record_ids,
            duplicate_record_ids = excluded.duplicate_record_ids,
            errors = excluded.errors,
            applied_at = CASE
                WHEN ? THEN datetime('now')
                ELSE processed_messages.applied_at
            END,
            last_seen_at = datetime('now'),
            updated_at = datetime('now')
        """,
        (
            fingerprint.source_id,
            fingerprint.source_path,
            fingerprint.source_hash,
            fingerprint.source_mtime,
            status,
            category,
            exclusion_reason,
            json.dumps(list(created_record_ids or [])),
            json.dumps(list(duplicate_record_ids or [])),
            json.dumps(list(errors or [])),
            1 if mark_applied else 0,
            1 if mark_applied else 0,
        ),
    )
    if commit:
        conn.commit()
    processed = get_processed_message(conn, fingerprint.source_id)
    assert processed is not None
    return processed


def _decode_int_list(raw: str | None) -> list[int]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    result: list[int] = []
    for value in data:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _decode_str_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(value) for value in data]
