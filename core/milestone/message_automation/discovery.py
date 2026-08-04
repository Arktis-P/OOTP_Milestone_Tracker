"""Discover ``messageN.txt`` inbox files and correlate ``messages.dat`` metadata.

This module is intentionally defensive: OOTP's binary ``messages.dat`` layout
is not documented anywhere in this repository and no verified binary sample
exists (see ``core/validation/season_replay.py``, which already ships a
"binary messages.dat parsing is not implemented" fallback). Rather than guess
at an unproven binary format, this module only understands metadata sidecars
that are structurally self-describing -- JSON objects or CSV rows -- and
sniffs their content instead of trusting the ``.dat`` extension, since a real
``messages.dat`` has no extension hint of its own. Anything else degrades to
``format="unsupported"`` with a warning instead of raising, and file
discovery/classification continues using per-file fingerprints alone.

Filename discovery deliberately uses a strict ``message<digits>.txt`` regex
(case-insensitive) rather than a loose glob, so files like ``messages.txt`` or
``message_backup.txt`` are never mistaken for OOTP inbox messages.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .processed import (
    MessageSourceFingerprint,
    fingerprint_message_file,
    get_message_rescan_status,
)

# Exact OOTP inbox filename shape: "message" + digits + ".txt". No loose
# prefix/suffix matching (e.g. "messages.txt", "message1_old.txt" are not
# matched).
MESSAGE_FILENAME_RE = re.compile(r"^message(\d+)\.txt$", re.IGNORECASE)

MESSAGES_DAT_FILENAME = "messages.dat"

# Discovery-level status contract (distinct from the finer-grained
# `processed_messages.status` values in `processed.py`).
STATUS_NEW = "new"
STATUS_ALREADY_APPLIED = "already_applied"
STATUS_CHANGED = "changed_review_needed"
STATUS_EXCLUDED = "excluded"
STATUS_ERROR = "error"
STATUS_UNRESOLVED = "unresolved"

ALL_STATUSES = (
    STATUS_NEW,
    STATUS_ALREADY_APPLIED,
    STATUS_CHANGED,
    STATUS_EXCLUDED,
    STATUS_ERROR,
    STATUS_UNRESOLVED,
)

_RESCAN_STATUS_MAP = {
    "new": STATUS_NEW,
    "changed_review_needed": STATUS_CHANGED,
    "already_applied": STATUS_ALREADY_APPLIED,
    "excluded": STATUS_EXCLUDED,
    "error": STATUS_ERROR,
}

_DATE_COLUMNS = ("date", "message_date", "event_date")
_KEY_COLUMNS = ("source_id", "source", "filename", "message", "id")


def classify_rescan_status(raw_status: str) -> str:
    """Map a `processed.get_message_rescan_status` value onto the six-state
    discovery contract (new/already_applied/changed/excluded/error/unresolved).

    Anything not explicitly new/changed/already_applied/excluded/error (e.g.
    ``candidate``, ``duplicate``, ``skipped``) is ``unresolved`` -- it exists
    but needs a person to look at it before it counts as done.
    """

    return _RESCAN_STATUS_MAP.get(raw_status, STATUS_UNRESOLVED)


@dataclass(frozen=True)
class MessageMetadataEntry:
    """One correlatable row from a parsed ``messages.dat`` sidecar."""

    key: str
    message_id: int | None
    message_date: date | None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MessagesDatParseResult:
    """Result of attempting to read a ``messages.dat`` metadata sidecar."""

    path: Path | None
    format: str  # "json" | "csv" | "missing" | "unsupported"
    entries: dict[str, MessageMetadataEntry] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def lookup(self, source_id: str, filename: str) -> MessageMetadataEntry | None:
        for key in (source_id, filename, filename.lower(), source_id.lower()):
            entry = self.entries.get(key)
            if entry is not None:
                return entry
        return None


def parse_messages_dat(path: str | Path | None) -> MessagesDatParseResult:
    """Defensively parse a ``messages.dat`` metadata sidecar.

    Only JSON objects and header CSV are understood, detected by content, not
    by the ``.dat`` extension (a real OOTP save has no extension signal). Any
    other content -- including an actual binary layout, if one exists --
    degrades to ``format="unsupported"`` with a warning rather than raising,
    so a missing/garbled metadata file never stops message discovery.
    """

    if path is None:
        return MessagesDatParseResult(path=None, format="missing")
    dat_path = Path(path)
    if not dat_path.is_file():
        return MessagesDatParseResult(path=dat_path, format="missing")

    try:
        raw_bytes = dat_path.read_bytes()
    except OSError as exc:
        return MessagesDatParseResult(
            path=dat_path,
            format="unsupported",
            warnings=[f"could not read {dat_path.name}: {exc}"],
        )

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = None

    if text is not None:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            json_result = _parse_json_metadata(stripped)
            if json_result is not None:
                entries, warnings = json_result
                return MessagesDatParseResult(
                    path=dat_path, format="json", entries=entries, warnings=warnings
                )
        csv_result = _parse_csv_metadata(text)
        if csv_result is not None:
            entries, warnings = csv_result
            return MessagesDatParseResult(
                path=dat_path, format="csv", entries=entries, warnings=warnings
            )

    return MessagesDatParseResult(
        path=dat_path,
        format="unsupported",
        warnings=[
            f"{dat_path.name} format not recognized (no JSON/CSV structure "
            "detected); per-file message dates are unavailable and "
            "date-dependent categories will need a manually supplied date"
        ],
    )


def _parse_json_metadata(
    text: str,
) -> tuple[dict[str, MessageMetadataEntry], list[str]] | None:
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    warnings: list[str] = []
    pairs: list[tuple[str, Any]] = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        for index, row in enumerate(raw):
            if isinstance(row, Mapping):
                row_key = row.get("source_id") or row.get("id") or row.get("filename") or row.get("message")
                if row_key is None:
                    warnings.append(f"skipped messages.dat list entry {index}: no id/filename/source_id key")
                    continue
                pairs.append((str(row_key), row))
            else:
                warnings.append(f"skipped unrecognized messages.dat list entry at index {index}")
    else:
        return None

    entries: dict[str, MessageMetadataEntry] = {}
    for raw_key, value in pairs:
        entry = _build_metadata_entry(str(raw_key), value)
        if entry is None:
            warnings.append(f"skipped unresolved messages.dat entry for {raw_key!r}")
            continue
        entries[entry.key] = entry
    return entries, warnings


def _parse_csv_metadata(
    text: str,
) -> tuple[dict[str, MessageMetadataEntry], list[str]] | None:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None
    key_col = _first_present(reader.fieldnames, _KEY_COLUMNS)
    date_col = _first_present(reader.fieldnames, _DATE_COLUMNS)
    if key_col is None:
        return None

    entries: dict[str, MessageMetadataEntry] = {}
    warnings: list[str] = []
    for row_index, row in enumerate(reader):
        raw_key = str(row.get(key_col, "") or "").strip()
        if not raw_key:
            continue
        date_value = str(row.get(date_col, "") or "").strip() if date_col else ""
        parsed_date = _try_parse_date(date_value) if date_value else None
        if date_value and parsed_date is None:
            warnings.append(f"unresolved date {date_value!r} on messages.dat row {row_index}")
        entries[_normalize_key(raw_key)] = MessageMetadataEntry(
            key=_normalize_key(raw_key),
            message_id=_extract_message_id(raw_key),
            message_date=parsed_date,
            raw=dict(row),
        )
    return entries, warnings


def _build_metadata_entry(key: str, value: Any) -> MessageMetadataEntry | None:
    normalized_key = _normalize_key(key)
    message_id = _extract_message_id(key)
    if isinstance(value, str):
        return MessageMetadataEntry(
            key=normalized_key,
            message_id=message_id,
            message_date=_try_parse_date(value),
            raw={"date": value},
        )
    if isinstance(value, Mapping):
        date_value = value.get("date") or value.get("message_date") or value.get("event_date")
        raw_id = value.get("id") or value.get("message_id")
        if raw_id is not None:
            try:
                message_id = int(raw_id)
            except (TypeError, ValueError):
                pass
        return MessageMetadataEntry(
            key=normalized_key,
            message_id=message_id,
            message_date=_try_parse_date(str(date_value)) if date_value else None,
            raw=dict(value),
        )
    return None


def _first_present(fieldnames: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _normalize_key(key: str) -> str:
    key = key.strip()
    if key.lower().endswith(".txt"):
        key = key[: -len(".txt")]
    return key


def _extract_message_id(key: str) -> int | None:
    match = re.search(r"(\d+)", key)
    return int(match.group(1)) if match else None


def _try_parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def discover_message_txt_files(directory: str | Path) -> list[Path]:
    """List ``messageN.txt`` files under ``directory``, deterministically
    ordered by numeric message id then filename (never OS iteration order).
    """

    directory = Path(directory)
    if not directory.is_dir():
        return []
    matches: list[tuple[int, str, Path]] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        match = MESSAGE_FILENAME_RE.match(entry.name)
        if not match:
            continue
        matches.append((int(match.group(1)), entry.name.lower(), entry))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in matches]


@dataclass(frozen=True)
class DiscoveredMessage:
    """One ``messageN.txt`` file, correlated with ``messages.dat`` if matched."""

    source_id: str
    message_id: int
    path: Path
    message_date: date | None
    metadata_matched: bool


@dataclass(frozen=True)
class MessageDiscoveryScan:
    """Result of scanning one messages directory for txt files + metadata."""

    directory: Path
    messages: list[DiscoveredMessage]
    metadata: MessagesDatParseResult
    orphan_metadata_keys: list[str]
    warnings: list[str]


def discover_messages(
    directory: str | Path,
    *,
    messages_dat_path: str | Path | None = None,
) -> MessageDiscoveryScan:
    """Discover ``messageN.txt`` files and correlate them against
    ``messages.dat`` metadata (when readable).

    ``messages_dat_path`` defaults to ``<directory>/messages.dat``, falling
    back to ``<directory's parent>/messages.dat`` (OOTP save layouts are not
    consistent about which level the file lives at). An unreadable or absent
    metadata file never prevents txt discovery -- every message is still
    returned, just without a correlated ``message_date``.
    """

    directory = Path(directory)
    dat_path = (
        Path(messages_dat_path)
        if messages_dat_path is not None
        else _default_messages_dat_path(directory)
    )
    metadata = parse_messages_dat(dat_path)

    messages: list[DiscoveredMessage] = []
    matched_keys: set[str] = set()
    for path in discover_message_txt_files(directory):
        match = MESSAGE_FILENAME_RE.match(path.name)
        assert match is not None
        source_id = path.stem
        entry = metadata.lookup(source_id, path.name)
        if entry is not None:
            matched_keys.add(entry.key)
        messages.append(
            DiscoveredMessage(
                source_id=source_id,
                message_id=int(match.group(1)),
                path=path,
                message_date=entry.message_date if entry is not None else None,
                metadata_matched=entry is not None,
            )
        )

    orphan_metadata_keys = sorted(key for key in metadata.entries if key not in matched_keys)

    warnings = list(metadata.warnings)
    if metadata.format == "missing" and dat_path is not None:
        warnings.append(
            f"{MESSAGES_DAT_FILENAME} not found under {directory}; per-file "
            "message dates are unavailable for date-dependent categories"
        )

    return MessageDiscoveryScan(
        directory=directory,
        messages=messages,
        metadata=metadata,
        orphan_metadata_keys=orphan_metadata_keys,
        warnings=warnings,
    )


def _default_messages_dat_path(directory: Path) -> Path | None:
    candidate = directory / MESSAGES_DAT_FILENAME
    if candidate.is_file():
        return candidate
    parent_candidate = directory.parent / MESSAGES_DAT_FILENAME
    if parent_candidate.is_file():
        return parent_candidate
    return candidate


@dataclass(frozen=True)
class MessageScanEntry:
    """One discovered message, classified against `processed_messages`."""

    source_id: str
    message_id: int
    path: Path
    message_date: date | None
    metadata_matched: bool
    fingerprint: MessageSourceFingerprint
    status: str


def scan_message_directory(
    conn: Any,
    directory: str | Path,
    *,
    messages_dat_path: str | Path | None = None,
) -> list[MessageScanEntry]:
    """Discover + classify every message under ``directory``.

    Each file is fingerprinted (hash-first change detection, via
    `processed.fingerprint_message_file`/`get_message_rescan_status`) and
    classified into the six-state discovery contract. A single unreadable
    file (e.g. removed/locked mid-scan) degrades to `STATUS_ERROR` for that
    entry only -- it never aborts the rest of the scan.
    """

    scan = discover_messages(directory, messages_dat_path=messages_dat_path)
    entries: list[MessageScanEntry] = []
    for message in scan.messages:
        try:
            fingerprint = fingerprint_message_file(message.path)
        except OSError:
            entries.append(
                MessageScanEntry(
                    source_id=message.source_id,
                    message_id=message.message_id,
                    path=message.path,
                    message_date=message.message_date,
                    metadata_matched=message.metadata_matched,
                    fingerprint=MessageSourceFingerprint(
                        source_id=message.source_id,
                        source_path=str(message.path),
                        source_hash="",
                        source_mtime=0.0,
                    ),
                    status=STATUS_ERROR,
                )
            )
            continue
        rescan_status = get_message_rescan_status(conn, fingerprint)
        entries.append(
            MessageScanEntry(
                source_id=message.source_id,
                message_id=message.message_id,
                path=message.path,
                message_date=message.message_date,
                metadata_matched=message.metadata_matched,
                fingerprint=fingerprint,
                status=classify_rescan_status(rescan_status),
            )
        )
    return entries


def filter_scan_entries(
    entries: Iterable[MessageScanEntry],
    *,
    statuses: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[MessageScanEntry]:
    """Filter scanned entries by status set and/or an inclusive date range.

    An entry with no correlated ``message_date`` is excluded by any active
    date filter -- an unknown date can't be known to fall inside a range.
    """

    allowed_statuses = set(statuses) if statuses is not None else None
    result: list[MessageScanEntry] = []
    for entry in entries:
        if allowed_statuses is not None and entry.status not in allowed_statuses:
            continue
        if date_from is not None or date_to is not None:
            if entry.message_date is None:
                continue
            if date_from is not None and entry.message_date < date_from:
                continue
            if date_to is not None and entry.message_date > date_to:
                continue
        result.append(entry)
    return result
