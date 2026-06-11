"""OOTP saved_games root auto-detection."""

from __future__ import annotations

import os
import string
from dataclasses import dataclass
from pathlib import Path

OOTP_VERSION_MIN = 20
OOTP_VERSION_MAX = 26
SAVED_GAMES_DIRNAME = "saved_games"
OOTP_FOLDER_PREFIX = "OOTP Baseball "


@dataclass(frozen=True)
class DetectedSaveRoot:
    path: Path
    ootp_version: int
    source: str  # "auto" | "manual"


def detect_save_roots() -> list[DetectedSaveRoot]:
    """Search common OOTP install locations and return all valid save roots."""
    found: list[DetectedSaveRoot] = []
    seen: set[Path] = set()

    for candidate in _candidate_documents_dirs():
        for version in range(OOTP_VERSION_MIN, OOTP_VERSION_MAX + 1):
            save_root = (
                candidate
                / "Out of the Park Developments"
                / f"{OOTP_FOLDER_PREFIX}{version}"
                / SAVED_GAMES_DIRNAME
            )
            if save_root in seen:
                continue
            if is_valid_save_root(save_root):
                seen.add(save_root)
                found.append(
                    DetectedSaveRoot(
                        path=save_root.resolve(),
                        ootp_version=version,
                        source="auto",
                    )
                )

    return sorted(found, key=lambda item: (-item.ootp_version, str(item.path)))


def infer_ootp_version_from_path(path: str | Path) -> int | None:
    """Extract OOTP version number from a path segment, if present."""
    text = str(path).replace("\\", "/")
    marker = OOTP_FOLDER_PREFIX
    idx = text.find(marker)
    if idx < 0:
        return None
    tail = text[idx + len(marker) :]
    digits = []
    for char in tail:
        if char.isdigit():
            digits.append(char)
        else:
            break
    if not digits:
        return None
    version = int("".join(digits))
    if OOTP_VERSION_MIN <= version <= OOTP_VERSION_MAX:
        return version
    return None


def is_valid_save_root(path: str | Path) -> bool:
    """Return True if path looks like an OOTP saved_games directory."""
    root = Path(path)
    if not root.is_dir():
        return False

    if _has_league_file_marker(root):
        return True

    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.suffix.lower() == ".lg":
            return True
        if _looks_like_league_folder(child):
            return True

    return False


def _candidate_documents_dirs() -> list[Path]:
    candidates: list[Path] = []

    home = Path.home()
    documents = home / "Documents"
    if documents.is_dir():
        candidates.append(documents)

    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            user_docs = Path(userprofile) / "Documents"
            if user_docs.is_dir() and user_docs not in candidates:
                candidates.append(user_docs)

        for drive in string.ascii_uppercase:
            drive_docs = Path(f"{drive}:/Users") / os.environ.get("USERNAME", "") / "Documents"
            if drive_docs.is_dir() and drive_docs not in candidates:
                candidates.append(drive_docs)

            drive_root_docs = Path(f"{drive}:/Documents")
            if drive_root_docs.is_dir() and drive_root_docs not in candidates:
                candidates.append(drive_root_docs)

    return candidates


def _has_league_file_marker(root: Path) -> bool:
    league_file = root / "league_file"
    return league_file.exists()


def _looks_like_league_folder(folder: Path) -> bool:
    expected = ("news", "rosters", "import_export")
    return sum(1 for name in expected if (folder / name).is_dir()) >= 2
