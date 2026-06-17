"""Tests for bundle update manifest scanning and merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import bundle_updates as bu
from core.milestone.definitions import load_milestones

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def bundle_user_dirs(monkeypatch, tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle_data = bundle / "data"
    bundle_data.mkdir(parents=True)
    user_dir = tmp_path / "userdata"
    user_dir.mkdir()

    (bundle / "version.txt").write_text("0.1.8\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "releases": [
            {
                "app_version": "0.1.8",
                "files": {
                    "milestones.csv": {
                        "added_keys": ["new_milestone_key", "existing_key"],
                    },
                    "streak_policies.json": {
                        "added_paths": ["batting.new_streak"],
                    },
                    "korean_last_names.csv": {
                        "added_names": ["NewLast"],
                    },
                    "korean_first_names.csv": {
                        "added_names": [],
                    },
                },
            }
        ],
    }
    (bundle_data / "bundle_updates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (bundle_data / "milestones.csv").write_text(
        "category,key,label,scope,stat,threshold,direction,grade,track_from,near_n,description_template\n"
        "batting,existing_key,기존,game,h,1,higher,common,,,batting_cumulative\n"
        "batting,new_milestone_key,신규,game,h,2,higher,common,,,batting_cumulative\n",
        encoding="utf-8",
    )
    (user_dir / "milestones.csv").write_text(
        "category,key,label,scope,stat,threshold,direction,grade,track_from,near_n,description_template\n"
        "batting,existing_key,기존,game,h,1,higher,common,,,batting_cumulative\n",
        encoding="utf-8",
    )

    (bundle_data / "streak_policies.json").write_text(
        json.dumps(
            {
                "labels": {"new_streak": "새 연속"},
                "batting": {"new_streak": {"fixed_milestones": [5]}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (user_dir / "streak_policies.json").write_text(
        '{"labels": {}, "batting": {}}',
        encoding="utf-8",
    )

    (bundle_data / "korean_last_names.csv").write_text(
        "last_name,korean\nNewLast,뉴라스트\n",
        encoding="utf-8",
    )
    (user_dir / "korean_last_names.csv").write_text(
        "last_name,korean\nOldLast,올드\n",
        encoding="utf-8",
    )
    (bundle_data / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8",
    )
    (user_dir / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8",
    )

    import core.config.paths as paths

    monkeypatch.setattr(paths, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(bu, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(bu, "get_user_data_dir", lambda: user_dir)
    paths._USER_DATA_READY = True

    return bundle, user_dir


def test_scan_pending_updates_lists_only_missing_items(bundle_user_dirs) -> None:
    _bundle, _user = bundle_user_dirs
    report = bu.scan_pending_updates()
    keys = {item.item_key for item in report.items}
    files = {item.file_name for item in report.items}

    assert report.total == 3
    assert "new_milestone_key" in keys
    assert "existing_key" not in keys
    assert "batting.new_streak" in keys
    assert "NewLast" in keys
    assert bu.MILESTONES_FILE in files


def test_apply_pending_updates_merges_without_overwriting(bundle_user_dirs) -> None:
    _bundle, user_dir = bundle_user_dirs
    result = bu.apply_pending_updates()
    assert result.applied_count == 3
    assert not result.errors

    local = load_milestones(user_dir / "milestones.csv")
    assert local.get_by_key("existing_key") is not None
    assert local.get_by_key("new_milestone_key") is not None

    streak = json.loads((user_dir / "streak_policies.json").read_text(encoding="utf-8"))
    assert streak["batting"]["new_streak"]["fixed_milestones"] == [5]

    names = (user_dir / "korean_last_names.csv").read_text(encoding="utf-8")
    assert "NewLast" in names
    assert "OldLast" in names

    report_after = bu.scan_pending_updates()
    assert report_after.total == 0

    state = bu.load_state()
    assert "0.1.8" in state.get("applied_versions", [])


def test_future_manifest_release_is_ignored(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle_data = bundle / "data"
    bundle_data.mkdir(parents=True)
    user_dir = tmp_path / "user"
    user_dir.mkdir()

    (bundle / "version.txt").write_text("0.1.7\n", encoding="utf-8")
    (bundle_data / "bundle_updates.json").write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "app_version": "0.1.9",
                        "files": {
                            "milestones.csv": {"added_keys": ["future_key"]},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (bundle_data / "milestones.csv").write_text(
        "category,key,label,scope,stat,threshold,direction,grade,track_from,near_n,description_template\n"
        "batting,future_key,미래,game,h,1,higher,common,,,batting_cumulative\n",
        encoding="utf-8",
    )
    (user_dir / "milestones.csv").write_text(
        "category,key,label,scope,stat,threshold,direction,grade,track_from,near_n,description_template\n",
        encoding="utf-8",
    )

    import core.config.paths as paths

    monkeypatch.setattr(paths, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(bu, "get_bundle_root", lambda: bundle)
    monkeypatch.setattr(bu, "get_user_data_dir", lambda: user_dir)
    paths._USER_DATA_READY = True

    assert bu.scan_pending_updates().total == 0
