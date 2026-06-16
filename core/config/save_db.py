"""Per-save SQLite database path helpers."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from core.config.paths import resolve_data_path

_LEGACY_DB_RELATIVE_PATHS = ("records.db", "data/records.db")


def save_db_slug(save_path: str | Path) -> str:
    """Stable folder name for one OOTP league save."""
    path = Path(save_path)
    resolved = str(path.resolve()).lower()
    label = re.sub(r"[^\w\-.]+", "_", path.name).strip("._") or "save"
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:10]
    return f"{label}_{digest}"


def save_db_relative_path(save_path: str | Path) -> str:
    """Settings-relative DB path for a league save."""
    return f"saves/{save_db_slug(save_path)}/records.db"


def resolve_save_db_path(save_path: str | Path) -> Path:
    return resolve_data_path(save_db_relative_path(save_path))


def migrate_legacy_shared_db(save_path: str | Path) -> Path:
    """Copy the old single shared records.db into this save's DB once."""
    target = resolve_save_db_path(save_path)
    if target.is_file():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    for relative in _LEGACY_DB_RELATIVE_PATHS:
        legacy = resolve_data_path(relative)
        if legacy.is_file() and legacy.resolve() != target.resolve():
            shutil.copy2(legacy, target)
            return target

    return target
