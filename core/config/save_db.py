"""Per-save SQLite database path helpers."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from core.config import paths as paths_module
from core.db.schema import init_database

_LEGACY_DB_RELATIVE_PATHS = ("records.db", "data/records.db")
_LEGACY_MIGRATION_FLAG = ".legacy_shared_db_migrated"


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
    return paths_module.resolve_data_path(save_db_relative_path(save_path))


def migrate_legacy_shared_db(save_path: str | Path) -> Path:
    """Ensure the per-save DB file exists.

    One-time upgrade only: copy the old shared ``records.db`` into the first
    league save that needs a database. Every other save starts empty.
    """
    target = resolve_save_db_path(save_path)
    if target.is_file():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    flag = paths_module.get_user_data_dir() / _LEGACY_MIGRATION_FLAG

    if not flag.is_file():
        for relative in _LEGACY_DB_RELATIVE_PATHS:
            legacy = paths_module.resolve_data_path(relative)
            if legacy.is_file() and legacy.resolve() != target.resolve():
                shutil.copy2(legacy, target)
                flag.write_text(str(target.resolve()), encoding="utf-8")
                return target

    init_database(target)
    return target
