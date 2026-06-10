"""Parse OOTP box score TXT files."""

from __future__ import annotations

from pathlib import Path

from core.stats.models import GameLog


class BoxScoreTxtParseError(Exception):
    """Raised when TXT box score parsing fails."""


def parse_boxscore_txt(file_path: str | Path) -> GameLog:
    """Parse an OOTP TXT box score file into a GameLog.

    Raises:
        BoxScoreTxtParseError: If the file cannot be parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise BoxScoreTxtParseError(f"File not found: {path}")

    # TODO(Phase 1): Implement TXT parsing against real OOTP sample files.
    raise BoxScoreTxtParseError(
        f"TXT box score parser not yet implemented: {path.name}"
    )
