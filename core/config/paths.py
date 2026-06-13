"""Application, bundle, and user-writable data path resolution."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "OOTP_Milestone_Tracker"

# Shipped inside the PyInstaller bundle (or repo data/ in dev). Copied on first run only.
BUNDLE_DATA_FILES = (
    "milestones.csv",
    "settings.json.example",
    "korean_last_names.csv",
    "korean_first_names.csv",
    "korean_names_pending.csv",
)

_USER_DATA_READY = False


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    """Read-only app root (source tree or PyInstaller _MEIPASS)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent.parent


def get_project_root() -> Path:
    """Backward-compatible alias for :func:`get_bundle_root`."""
    return get_bundle_root()


def get_user_data_dir() -> Path:
    """Writable user data directory (persists across app updates)."""
    if is_frozen():
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / APP_DIR_NAME
    return get_bundle_root() / "data"


def _normalize_data_relative(relative: str) -> str:
    text = relative.replace("\\", "/").strip("/")
    if text.startswith("data/"):
        return text[len("data/") :]
    return text


def _legacy_user_data_dir() -> Path | None:
    if not is_frozen():
        return None
    legacy = Path(sys.executable).resolve().parent / "_internal" / "data"
    return legacy if legacy.is_dir() else None


def _maybe_migrate_legacy_user_data(user_dir: Path) -> None:
    """One-time copy from pre-0.2 in-bundle data/ to external user dir."""
    if user_dir.exists() and any(user_dir.iterdir()):
        return
    legacy = _legacy_user_data_dir()
    if legacy is None:
        return
    user_dir.mkdir(parents=True, exist_ok=True)
    for path in legacy.iterdir():
        dest = user_dir / path.name
        if dest.exists():
            continue
        if path.is_file():
            shutil.copy2(path, dest)


def ensure_user_data_dir() -> Path:
    """Create user data dir and seed missing default files from the bundle."""
    global _USER_DATA_READY
    user_dir = get_user_data_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    _maybe_migrate_legacy_user_data(user_dir)

    bundle_data = get_bundle_root() / "data"
    for name in BUNDLE_DATA_FILES:
        dest = user_dir / name
        if dest.is_file():
            continue
        src = bundle_data / name
        if src.is_file():
            shutil.copy2(src, dest)

    _USER_DATA_READY = True
    return user_dir


def resolve_data_path(relative: str) -> Path:
    """Resolve a settings-relative path (e.g. ``data/records.db``) under user data."""
    if not _USER_DATA_READY:
        ensure_user_data_dir()
    return get_user_data_dir() / _normalize_data_relative(relative)


def default_settings_path() -> Path:
    return resolve_data_path("data/settings.json")
