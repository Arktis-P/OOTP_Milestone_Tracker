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

from .parser import ParsedMessage, parse_message
from .recorder import apply_parsed_messages, record_parsed_message
from .service import (
    MessageImportResult,
    import_message_file,
    import_message_files,
    import_message_text,
)

__all__ = [
    "ParsedMessage",
    "MessageImportResult",
    "apply_parsed_messages",
    "import_message_file",
    "import_message_files",
    "import_message_text",
    "parse_message",
    "record_parsed_message",
]
