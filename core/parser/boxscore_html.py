"""Parse OOTP box score HTML files."""

from __future__ import annotations

from pathlib import Path

from core.stats.models import GameLog


class BoxScoreHtmlParseError(Exception):
    """Raised when HTML box score parsing fails."""


def parse_boxscore_html(file_path: str | Path) -> GameLog:
    """Parse an OOTP HTML box score file into a GameLog.

    Raises:
        BoxScoreHtmlParseError: If the file cannot be parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise BoxScoreHtmlParseError(f"File not found: {path}")

    # TODO(Phase 1): Implement HTML parsing against real OOTP sample files.
    raise BoxScoreHtmlParseError(
        f"HTML box score parser not yet implemented: {path.name}"
    )
