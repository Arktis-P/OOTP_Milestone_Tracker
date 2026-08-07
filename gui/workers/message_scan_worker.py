"""Background workers for OOTP news-message scanning and applying.

Both phases open their own SQLite connection (mirroring
``gui.workers.import_worker.ImportWorker``) so file I/O, parsing, and record
persistence never block the UI thread. Progress is reported per file/message
and cancellation is cooperative (checked between items), matching the
established box score import worker pattern.

Discovery uses the committed
``core.milestone.message_automation.discovery.discover_messages`` API, which
correlates each ``messageN.txt`` file against a ``messages.dat`` metadata
sidecar (when one is present and readable) to recover a per-message date --
that date is fed into ``parse_message`` so date-dependent categories can
resolve directly instead of always landing on ``date_needed``.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.config.settings_manager import AppSettings
from core.i18n import tr
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.message_automation.discovery import (
    DiscoveredMessage,
    discover_messages,
)
from core.milestone.message_automation.parser import ParsedMessage, parse_message
from core.milestone.message_automation.processed import (
    MessageSourceFingerprint,
    fingerprint_message_file,
    get_message_rescan_status,
    get_processed_message,
    upsert_processed_message,
)
from core.milestone.message_automation.recorder import record_parsed_message_result
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
from gui.widgets.message_review_model import (
    STATUS_APPLIED,
    STATUS_DATE_NEEDED,
    STATUS_EXCLUDED,
    MessageReviewItem,
)


SCAN_NEW = "new"
SCAN_CHANGED = "changed_review_needed"
SCAN_EXCLUDED = "excluded"
SCAN_ALREADY_APPLIED = "already_applied"
SCAN_DATE_NEEDED = "date_needed"
SCAN_ERROR = "error"

SCAN_STATUS_KEYS = (
    SCAN_NEW,
    SCAN_CHANGED,
    SCAN_EXCLUDED,
    SCAN_ALREADY_APPLIED,
    SCAN_DATE_NEEDED,
    SCAN_ERROR,
)


class MessageWorkflowCancelled(RuntimeError):
    """Raised internally so a worker's ``with Aggregator(...)`` block rolls
    back any not-yet-committed writes for the current run atomically."""


@dataclass
class MessageScanRow:
    """One scanned file's classification, independent of the review item's
    own approve/save lifecycle (``MessageReviewItem.status``)."""

    item: MessageReviewItem
    fingerprint: MessageSourceFingerprint | None
    scan_status: str


@dataclass
class MessageScanPayload:
    items: list[MessageReviewItem] = field(default_factory=list)
    fingerprints: dict[str, MessageSourceFingerprint] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    expected_count: int = 0


ScanFileFn = Callable[[sqlite3.Connection, DiscoveredMessage, "list[str]", "int | None"], MessageScanRow]


def discover_message_candidates(directories: list[Path]) -> list[DiscoveredMessage]:
    """Discover + messages.dat-correlate every message under ``directories``.

    Later directories never shadow an already-seen ``source_id`` -- a save's
    layout can list more than one messages folder and a given inbox message
    should only be scanned once.
    """

    discovered: list[DiscoveredMessage] = []
    seen_ids: set[str] = set()
    for directory in directories:
        scan = discover_messages(directory)
        for message in scan.messages:
            if message.source_id in seen_ids:
                continue
            seen_ids.add(message.source_id)
            discovered.append(message)
    return discovered


def scan_message_file(
    conn: sqlite3.Connection,
    message: DiscoveredMessage,
    tracked_teams: list[str],
    season_hint: int | None,
) -> MessageScanRow:
    """Default per-file scan: fingerprint, resolve rescan state, parse.

    ``message.message_date`` (resolved from ``messages.dat`` correlation, if
    any) is passed into the parser so date-dependent categories can resolve
    to a ready candidate instead of always requiring a manual date.

    Policy-excluded messages (tracked-team mismatch, non-recordable
    category, ...) are persisted immediately so the next scan does not
    resurface the same unchanged file as ``new`` -- mirroring how an
    explicit reviewer exclusion is already made durable.
    """

    path = message.path
    raw = ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        fingerprint = fingerprint_message_file(path)
        rescan_status = get_message_rescan_status(conn, fingerprint)
        processed = get_processed_message(conn, path.stem)
        parsed = parse_message(
            raw,
            tracked_teams=tracked_teams,
            message_date=message.message_date,
            season_hint=season_hint,
            source_id=path.stem,
        )
        item = MessageReviewItem(parsed, raw_text=raw)
        if message.message_date is not None:
            item.message_date = message.message_date

        if rescan_status == "already_applied" and processed is not None:
            item.status = STATUS_APPLIED
            item.created_record_ids = list(processed.created_record_ids)
            item.duplicate_record_ids = list(processed.duplicate_record_ids)
            scan_status = SCAN_ALREADY_APPLIED
        elif rescan_status == "changed_review_needed":
            item.notice = "changed_source"
            scan_status = SCAN_CHANGED
        elif rescan_status == "excluded":
            # A policy exclusion (such as a custom team's abbreviation not
            # yet being expanded to its display name) must not permanently
            # hide an unchanged message after the tracking configuration is
            # corrected.  A reviewer exclusion is an explicit decision and
            # remains durable.
            if (
                processed is not None
                and processed.exclusion_reason != "excluded_by_reviewer"
                and not parsed.excluded
            ):
                upsert_processed_message(
                    conn,
                    fingerprint=fingerprint,
                    status="candidate",
                    category=parsed.category,
                    commit=False,
                )
                scan_status = SCAN_NEW
            else:
                item.status = STATUS_EXCLUDED
                scan_status = SCAN_EXCLUDED
        elif item.status == STATUS_EXCLUDED:
            upsert_processed_message(
                conn,
                fingerprint=fingerprint,
                status="excluded",
                category=parsed.category,
                exclusion_reason=parsed.exclusion_reason,
                commit=False,
            )
            scan_status = SCAN_EXCLUDED
        elif item.status == STATUS_DATE_NEEDED:
            scan_status = SCAN_DATE_NEEDED
        else:
            scan_status = SCAN_NEW

        return MessageScanRow(item=item, fingerprint=fingerprint, scan_status=scan_status)
    except Exception as exc:  # pragma: no cover - defensive per-file path
        parsed = ParsedMessage(
            category="error",
            title=path.stem,
            excluded=True,
            exclusion_reason="file_read_failed",
            forms=[],
            source_id=path.stem,
            player_names={},
        )
        del exc
        item = MessageReviewItem(parsed, raw_text=raw, error="file_read_failed")
        return MessageScanRow(item=item, fingerprint=None, scan_status=SCAN_ERROR)


class MessageScanWorker(QThread):
    """Discover and scan OOTP ``messageN.txt`` files off the UI thread."""

    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object)  # MessageScanPayload
    cancelled = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: str | Path,
        directories: list[Path],
        *,
        tracked_teams: list[str] | None = None,
        custom_teams: dict[str, str] | None = None,
        season_hint: int | None = None,
        scan_file: ScanFileFn | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.directories = list(directories)
        self.tracked_teams = expand_tracked_teams(
            list(tracked_teams or []), custom_teams
        )
        self.season_hint = season_hint
        self._scan_file = scan_file or scan_message_file
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation before the next file is scanned."""
        self._cancel_event.set()
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or self.isInterruptionRequested()

    def run(self) -> None:
        payload = MessageScanPayload()
        payload.counts = dict.fromkeys(SCAN_STATUS_KEYS, 0)
        try:
            discovered = discover_message_candidates(self.directories)
            total = len(discovered)
            payload.expected_count = total
            with Aggregator(self.db_path) as aggregator:
                for index, message in enumerate(discovered, start=1):
                    if self._is_cancelled():
                        raise MessageWorkflowCancelled(
                            tr("Message scan cancelled by user.")
                        )
                    self.progress.emit(index, total, message.path.name)
                    row = self._scan_file(
                        aggregator.conn, message, self.tracked_teams, self.season_hint
                    )
                    payload.items.append(row.item)
                    if row.fingerprint is not None:
                        payload.fingerprints[row.item.source_id] = row.fingerprint
                    payload.counts[row.scan_status] = (
                        payload.counts.get(row.scan_status, 0) + 1
                    )
                aggregator.conn.commit()
        except MessageWorkflowCancelled as exc:
            self.cancelled.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.error.emit(str(exc))
            return
        self.completed.emit(payload)


@dataclass
class MessageApplyPayload:
    results: list[Any] = field(default_factory=list)
    created: int = 0
    duplicates: int = 0
    errors: int = 0


class MessageApplyWorker(QThread):
    """Persist approved parsed messages off the UI thread."""

    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object)  # MessageApplyPayload
    cancelled = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: str | Path,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parsed_messages: list[ParsedMessage],
        fingerprints: dict[str, MessageSourceFingerprint],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.milestones = milestones
        self.settings = settings
        self.parsed_messages = list(parsed_messages)
        self.fingerprints = dict(fingerprints)
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation before the next message is saved."""
        self._cancel_event.set()
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or self.isInterruptionRequested()

    def run(self) -> None:
        total = len(self.parsed_messages)
        payload = MessageApplyPayload()
        try:
            with Aggregator(self.db_path) as aggregator:
                checker = MilestoneChecker(
                    aggregator,
                    self.milestones,
                    season_games_total=self.settings.season_games_total,
                    ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                    tracked_teams=self.settings.tracked_teams,
                    custom_teams=self.settings.custom_mlb_teams,
                )
                for index, parsed in enumerate(self.parsed_messages, start=1):
                    if self._is_cancelled():
                        raise MessageWorkflowCancelled(tr("Save cancelled by user."))
                    self.progress.emit(index, total, parsed.title or parsed.source_id or "")
                    fingerprint = self.fingerprints.get(parsed.source_id or "")
                    result = record_parsed_message_result(
                        checker, parsed, fingerprint=fingerprint
                    )
                    payload.results.append(result)
                    payload.created += len(result.created_record_ids)
                    payload.duplicates += len(result.duplicate_record_ids)
                    payload.errors += len(result.errors)
        except MessageWorkflowCancelled as exc:
            # Messages already processed above were committed individually by
            # `record_parsed_message_result`; only the remaining tail is
            # skipped, so partial progress is preserved intentionally.
            self.cancelled.emit(str(exc), payload)
            return
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.completed.emit(payload)
