"""Per-save database path tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config.paths import resolve_data_path
from core.config.save_db import (
    migrate_legacy_shared_db,
    resolve_save_db_path,
    save_db_relative_path,
    save_db_slug,
)
from core.config.settings_manager import AppSettings, SettingsManager


def test_save_db_slug_is_stable_for_same_path(tmp_path: Path) -> None:
    save = tmp_path / "My League"
    save.mkdir()
    assert save_db_slug(save) == save_db_slug(save)


def test_save_db_slug_differs_for_different_paths(tmp_path: Path) -> None:
    save_a = tmp_path / "League A"
    save_b = tmp_path / "League B"
    save_a.mkdir()
    save_b.mkdir()
    assert save_db_slug(save_a) != save_db_slug(save_b)


def test_settings_derive_per_save_db_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_dir = tmp_path / "userdata"
    user_dir.mkdir()
    import core.config.paths as paths

    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(paths, "_USER_DATA_READY", True)

    save_path = tmp_path / "saves_root" / "MLB 2026"
    save_path.mkdir(parents=True)
    manager = SettingsManager(tmp_path / "settings.json")
    settings = manager.update_active_save(
        AppSettings(),
        save_root=str(tmp_path / "saves_root"),
        save_name="MLB 2026",
        save_path=str(save_path),
    )

    expected = save_db_relative_path(save_path)
    assert settings.db_path == expected
    assert resolve_data_path(settings.db_path) == resolve_save_db_path(save_path)


def test_legacy_shared_db_migrates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_dir = tmp_path / "userdata"
    user_dir.mkdir()
    legacy = user_dir / "records.db"
    legacy.write_bytes(b"legacy-db")

    import core.config.paths as paths

    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(paths, "_USER_DATA_READY", True)

    save_path = tmp_path / "MLB"
    save_path.mkdir()
    target = migrate_legacy_shared_db(save_path)
    assert target.is_file()
    assert target.read_bytes() == b"legacy-db"
    assert migrate_legacy_shared_db(save_path).resolve() == target.resolve()
