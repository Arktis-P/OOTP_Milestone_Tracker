"""File/text orchestration for OOTP message automation."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from core.milestone.checker import MilestoneChecker

from .discovery import MessageScanEntry
from .parser import ParsedMessage, parse_message
from .processed import (
    MessageApplyResult,
    fingerprint_message_file,
    fingerprint_message_text,
)
from .recorder import record_parsed_message_result


@dataclass(frozen=True)
class MessageImportResult:
    source_id: str
    parsed: ParsedMessage
    record_ids: list[int]
    duplicate_record_ids: list[int] | None = None
    errors: list[str] | None = None

    @property
    def recorded_count(self) -> int:
        return len(self.record_ids)

    @property
    def apply_result(self) -> MessageApplyResult:
        return MessageApplyResult(
            source_id=self.source_id,
            created_record_ids=list(self.record_ids),
            duplicate_record_ids=list(self.duplicate_record_ids or []),
            errors=list(self.errors or []),
        )


def import_message_text(
    checker: MilestoneChecker,
    text: str,
    *,
    message_date: date | None,
    season_hint: int | None = None,
    source_id: str | None = None,
    tracked_teams: list[str] | None = None,
) -> MessageImportResult:
    """Parse and persist one message through the existing manual APIs."""

    parsed = parse_message(
        text,
        tracked_teams=(
            list(checker.tracked_teams)
            if tracked_teams is None
            else tracked_teams
        ),
        message_date=message_date,
        season_hint=season_hint,
        source_id=source_id,
    )
    fingerprint = fingerprint_message_text(text, source_id=parsed.source_id or source_id)
    result = record_parsed_message_result(checker, parsed, fingerprint=fingerprint)
    return MessageImportResult(
        parsed.source_id or "",
        parsed,
        result.created_record_ids,
        result.duplicate_record_ids,
        result.errors,
    )


def import_message_file(
    checker: MilestoneChecker,
    path: str | Path,
    *,
    message_date: date | None,
    season_hint: int | None = None,
    tracked_teams: list[str] | None = None,
) -> MessageImportResult:
    """Read one UTF-8 OOTP ``messageN.txt`` file and import it."""

    message_path = Path(path)
    text = message_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_message(
        text,
        tracked_teams=(
            list(checker.tracked_teams)
            if tracked_teams is None
            else tracked_teams
        ),
        message_date=message_date,
        season_hint=season_hint,
        source_id=message_path.stem,
    )
    result = record_parsed_message_result(
        checker,
        parsed,
        fingerprint=fingerprint_message_file(message_path),
    )
    return MessageImportResult(
        parsed.source_id or "",
        parsed,
        result.created_record_ids,
        result.duplicate_record_ids,
        result.errors,
    )


def import_message_files(
    checker: MilestoneChecker,
    paths: Iterable[str | Path],
    *,
    message_dates: Mapping[str, date],
    season_hint: int | None = None,
    tracked_teams: list[str] | None = None,
) -> list[MessageImportResult]:
    """Import multiple messages using dates resolved from ``messages.dat``.

    ``message_dates`` may use a file name (``message1433.txt``) or stem
    (``message1433``) as its key. Missing dates remain ``None``; the parser
    then excludes event types for which the field contract requires an exact
    message date.
    """

    results: list[MessageImportResult] = []
    for raw_path in paths:
        path = Path(raw_path)
        message_date = message_dates.get(path.name) or message_dates.get(path.stem)
        results.append(
            import_message_file(
                checker,
                path,
                message_date=message_date,
                season_hint=season_hint,
                tracked_teams=tracked_teams,
            )
        )
    return results


class CancellationToken:
    """Cooperative cancellation flag for a running selected/batch apply.

    Deliberately not tied to Qt (this package stays GUI-agnostic) -- a caller
    running this from a worker thread just calls `.cancel()` from wherever it
    already reacts to a user cancel action.
    """

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True)
class BatchApplyOutcome:
    """Aggregated result of a selected/batch apply run."""

    total_requested: int
    results: list[MessageImportResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def processed_count(self) -> int:
        return len(self.results)

    @property
    def not_attempted_count(self) -> int:
        return self.total_requested - self.processed_count

    @property
    def created_count(self) -> int:
        return sum(result.recorded_count for result in self.results)

    @property
    def duplicate_count(self) -> int:
        return sum(len(result.duplicate_record_ids or []) for result in self.results)

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.errors)

    @property
    def excluded_count(self) -> int:
        return sum(1 for result in self.results if result.parsed.excluded)


def apply_selected_messages(
    checker: MilestoneChecker,
    entries: Iterable[MessageScanEntry],
    *,
    season_hint: int | None = None,
    tracked_teams: list[str] | None = None,
    cancellation: CancellationToken | None = None,
    on_progress: Callable[[int, int, MessageScanEntry], None] | None = None,
) -> BatchApplyOutcome:
    """Apply a caller-selected batch of discovered messages, in order.

    Cancellation is checked before each entry (not mid-entry), so a run that
    is cancelled after N files leaves exactly those N files' results --
    already-applied ones stay applied, nothing is rolled back. Reuses
    `import_message_file` for each entry, so persistence/duplicate-detection
    behavior is identical to a single manual import.
    """

    entries = list(entries)
    results: list[MessageImportResult] = []
    cancelled = False
    for index, entry in enumerate(entries, start=1):
        if cancellation is not None and cancellation.is_cancelled:
            cancelled = True
            break
        result = import_message_file(
            checker,
            entry.path,
            message_date=entry.message_date,
            season_hint=season_hint,
            tracked_teams=tracked_teams,
        )
        results.append(result)
        if on_progress is not None:
            on_progress(index, len(entries), entry)
    return BatchApplyOutcome(
        total_requested=len(entries), results=results, cancelled=cancelled
    )
