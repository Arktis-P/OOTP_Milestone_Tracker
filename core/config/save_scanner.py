"""Scan OOTP save root for valid league folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LEAGUE_MARKERS = ("news", "rosters", "import_export")


@dataclass(frozen=True)
class SaveEntry:
    name: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": str(self.path)}


def scan_saves(save_root: str | Path) -> list[SaveEntry]:
    """Return valid league folders under a saved_games root."""
    root = Path(save_root)
    if not root.is_dir():
        return []

    entries: list[SaveEntry] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if is_valid_league_folder(child):
            entries.append(SaveEntry(name=child.name, path=child.resolve()))
    return entries


def is_valid_league_folder(path: str | Path) -> bool:
    """Validate a league folder by OOTP standard subdirectories."""
    folder = Path(path)
    if not folder.is_dir():
        return False

    if folder.suffix.lower() == ".lg":
        return True

    if (folder / "league_file").exists():
        return True

    present = sum(1 for name in LEAGUE_MARKERS if (folder / name).is_dir())
    return present >= 2


def find_save_by_name(save_root: str | Path, name: str) -> SaveEntry | None:
    for entry in scan_saves(save_root):
        if entry.name == name:
            return entry
    return None
