"""OOTP inbox message automation (awards, trades, injuries, postseason, HOF).

Parses `messages/messageN.txt`-style OOTP inbox text into structured,
recordable results and routes valid ones through the existing manual-entry
persistence path (`core.milestone.checker.MilestoneChecker.record_manual_*`).
See `docs/message_automation_field_rules.md` for the field mapping this
module implements.

Public API::

    from core.milestone.message_automation import parse_message, record_parsed_message

    parsed = parse_message(text, tracked_teams=["Seoul Yukies"], message_date=my_date)
    if not parsed.excluded:
        record_parsed_message(checker, parsed)
"""

from __future__ import annotations

from .discovery import (
    ALL_STATUSES,
    STATUS_ALREADY_APPLIED,
    STATUS_CHANGED,
    STATUS_ERROR,
    STATUS_EXCLUDED,
    STATUS_NEW,
    STATUS_UNRESOLVED,
    DiscoveredMessage,
    MessageDiscoveryScan,
    MessageMetadataEntry,
    MessageScanEntry,
    MessagesDatParseResult,
    classify_rescan_status,
    discover_message_txt_files,
    discover_messages,
    filter_scan_entries,
    parse_messages_dat,
    scan_message_directory,
)
from .parser import ParsedMessage, parse_message
from .processed import (
    MessageApplyResult,
    ProcessedMessage,
    get_message_rescan_status,
    get_processed_message,
)
from .recorder import (
    apply_parsed_messages,
    record_parsed_message,
    record_parsed_message_result,
)
from .service import (
    BatchApplyOutcome,
    CancellationToken,
    MessageImportResult,
    apply_selected_messages,
    import_message_file,
    import_message_files,
    import_message_text,
)

__all__ = [
    "ParsedMessage",
    "MessageImportResult",
    "MessageApplyResult",
    "ProcessedMessage",
    "ALL_STATUSES",
    "STATUS_ALREADY_APPLIED",
    "STATUS_CHANGED",
    "STATUS_ERROR",
    "STATUS_EXCLUDED",
    "STATUS_NEW",
    "STATUS_UNRESOLVED",
    "BatchApplyOutcome",
    "CancellationToken",
    "DiscoveredMessage",
    "MessageDiscoveryScan",
    "MessageMetadataEntry",
    "MessageScanEntry",
    "MessagesDatParseResult",
    "apply_parsed_messages",
    "apply_selected_messages",
    "classify_rescan_status",
    "discover_message_txt_files",
    "discover_messages",
    "filter_scan_entries",
    "get_message_rescan_status",
    "get_processed_message",
    "import_message_file",
    "import_message_files",
    "import_message_text",
    "parse_message",
    "parse_messages_dat",
    "record_parsed_message",
    "record_parsed_message_result",
    "scan_message_directory",
]
