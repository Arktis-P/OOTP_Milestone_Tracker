"""Tests for user vs bundle data path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

from core.config.paths import (
    ensure_user_data_dir,
    get_bundle_root,
    get_user_data_dir,
    resolve_data_path,
)


def test_dev_mode_uses_project_data_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    fake_root = tmp_path / "app"
    data_dir = fake_root / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "milestones.csv").write_text("id\n", encoding="utf-8")

    import core.config.paths as paths

    monkeypatch.setattr(paths, "get_bundle_root", lambda: fake_root)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    paths._USER_DATA_READY = False

    assert get_user_data_dir() == data_dir
    assert resolve_data_path("data/records.db") == data_dir / "records.db"
    assert resolve_data_path("records.db") == data_dir / "records.db"


def test_frozen_mode_uses_appdata(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle_data = bundle / "data"
    bundle_data.mkdir(parents=True)
    (bundle_data / "milestones.csv").write_text("seed\n", encoding="utf-8")
    (bundle_data / "settings.json.example").write_text("{}", encoding="utf-8")
    (bundle_data / "korean_last_names.csv").write_text("last_name,korean\n", encoding="utf-8")
    (bundle_data / "korean_first_names.csv").write_text("first_name,korean\n", encoding="utf-8")
    (bundle_data / "korean_names_pending.csv.example").write_text(
        "part,name,source,first_seen\n", encoding="utf-8"
    )
    (bundle_data / "streak_policies.json").write_text('{"batting":{}}\n', encoding="utf-8")

    user_dir = tmp_path / "userdata"
    monkeypatch.setenv("APPDATA", str(tmp_path))

    import core.config.paths as paths

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(paths, "_maybe_migrate_legacy_user_data", lambda _dir: None)
    paths._USER_DATA_READY = False

    ensure_user_data_dir()

    assert (user_dir / "milestones.csv").read_text(encoding="utf-8") == "seed\n"
    assert (user_dir / "streak_policies.json").is_file()
    assert (user_dir / "korean_names_pending.csv").read_text(encoding="utf-8") == (
        "part,name,source,first_seen\n"
    )
    assert resolve_data_path("data/records.db") == user_dir / "records.db"


def test_legacy_data_migrated_once(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "dist" / "app"
    legacy = exe_dir / "_internal" / "data"
    legacy.mkdir(parents=True)
    (legacy / "records.db").write_bytes(b"sqlite")
    (legacy / "settings.json").write_text("{}", encoding="utf-8")

    user_dir = tmp_path / "Roaming" / "OOTP_Milestone_Tracker"
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    import core.config.paths as paths

    bundle = tmp_path / "bundle"
    (bundle / "data").mkdir(parents=True)

    monkeypatch.setattr(sys, "executable", str(exe_dir / "app.exe"))
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    paths._USER_DATA_READY = False

    ensure_user_data_dir()

    assert (user_dir / "records.db").read_bytes() == b"sqlite"
    assert (user_dir / "settings.json").is_file()
