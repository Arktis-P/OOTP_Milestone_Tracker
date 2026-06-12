"""In-memory cache for parsed OOTP roster export files."""

from __future__ import annotations

from pathlib import Path

from core.roster.ootp_format import OotpRosterFile, load_ootp_roster

_cache: dict[str, tuple[float, OotpRosterFile]] = {}


def load_ootp_roster_cached(file_path: str | Path) -> OotpRosterFile:
    """Return parsed roster; re-parse only when the file mtime changes."""
    path = Path(file_path).resolve()
    mtime = path.stat().st_mtime
    key = str(path)
    cached = _cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    roster = load_ootp_roster(path)
    _cache[key] = (mtime, roster)
    return roster


def invalidate_roster_cache(file_path: str | Path | None = None) -> None:
    if file_path is None:
        _cache.clear()
        return
    _cache.pop(str(Path(file_path).resolve()), None)
