"""File/text orchestration for OOTP message automation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from core.milestone.checker import MilestoneChecker

from .parser import ParsedMessage, parse_message
from .recorder import record_parsed_message


@dataclass(frozen=True)
class MessageImportResult:
    source_id: str
    parsed: ParsedMessage
    record_ids: list[int]

    @property
    def recorded_count(self) -> int:
        return len(self.record_ids)


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
    ids = record_parsed_message(checker, parsed)
    return MessageImportResult(parsed.source_id or "", parsed, ids)


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
    return import_message_text(
        checker,
        message_path.read_text(encoding="utf-8", errors="replace"),
        message_date=message_date,
        season_hint=season_hint,
        source_id=message_path.stem,
        tracked_teams=tracked_teams,
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
