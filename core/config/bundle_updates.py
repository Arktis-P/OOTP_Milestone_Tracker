"""Detect and merge bundle-shipped updates into user data files."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config.paths import get_bundle_root, get_user_data_dir, resolve_data_path
from core.i18n import tr
from core.milestone.definitions import load_milestones, save_milestones_csv

MANIFEST_NAME = "bundle_updates.json"
STATE_NAME = "bundle_updates_state.json"
VERSION_FILE = "version.txt"

MILESTONES_FILE = "milestones.csv"
STREAK_POLICIES_FILE = "streak_policies.json"
KOREAN_LAST_NAMES_FILE = "korean_last_names.csv"
KOREAN_FIRST_NAMES_FILE = "korean_first_names.csv"

FILE_LABELS: dict[str, str] = {
    MILESTONES_FILE: "Milestone Criteria",
    STREAK_POLICIES_FILE: "Streak Policies",
    KOREAN_LAST_NAMES_FILE: "Korean Last Name Mappings",
    KOREAN_FIRST_NAMES_FILE: "Korean First Name Mappings",
}


@dataclass(frozen=True)
class PendingBundleItem:
    app_version: str
    file_name: str
    item_key: str
    label: str


@dataclass
class BundleUpdateReport:
    app_version: str
    items: list[PendingBundleItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    def by_file(self) -> dict[str, list[PendingBundleItem]]:
        grouped: dict[str, list[PendingBundleItem]] = {}
        for item in self.items:
            grouped.setdefault(item.file_name, []).append(item)
        return grouped


@dataclass
class BundleApplyResult:
    applied_count: int = 0
    skipped_count: int = 0
    backed_up_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def get_app_version() -> str:
    path = get_bundle_root() / VERSION_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.0.0"


def bundle_manifest_path() -> Path:
    return get_bundle_root() / "data" / MANIFEST_NAME


def bundle_data_path(file_name: str) -> Path:
    return get_bundle_root() / "data" / file_name


def user_data_file_path(file_name: str) -> Path:
    return resolve_data_path(f"data/{file_name}")


def state_path() -> Path:
    return get_user_data_dir() / STATE_NAME


def load_manifest() -> dict[str, Any]:
    path = bundle_manifest_path()
    if not path.is_file():
        return {"schema_version": 1, "releases": []}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {"applied_versions": []}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def scan_pending_updates() -> BundleUpdateReport:
    manifest = load_manifest()
    app_version = get_app_version()
    items: list[PendingBundleItem] = []

    for release in manifest.get("releases") or []:
        release_version = str(release.get("app_version") or "").strip()
        if not release_version or _version_gt(release_version, app_version):
            continue
        files = release.get("files") or {}
        items.extend(
            _pending_milestone_items(release_version, files.get(MILESTONES_FILE) or {})
        )
        items.extend(
            _pending_streak_items(release_version, files.get(STREAK_POLICIES_FILE) or {})
        )
        items.extend(
            _pending_korean_name_items(
                release_version,
                KOREAN_LAST_NAMES_FILE,
                "last_name",
                files.get(KOREAN_LAST_NAMES_FILE) or {},
            )
        )
        items.extend(
            _pending_korean_name_items(
                release_version,
                KOREAN_FIRST_NAMES_FILE,
                "first_name",
                files.get(KOREAN_FIRST_NAMES_FILE) or {},
            )
        )

    return BundleUpdateReport(app_version=app_version, items=items)


def apply_pending_updates(
    items: list[PendingBundleItem] | None = None,
    *,
    backup: bool = True,
) -> BundleApplyResult:
    report = scan_pending_updates()
    target_items = items if items is not None else report.items
    result = BundleApplyResult()

    if not target_items:
        return result

    files_to_touch = sorted({item.file_name for item in target_items})
    if backup:
        for file_name in files_to_touch:
            local_path = user_data_file_path(file_name)
            if local_path.is_file():
                backup_path = _backup_path(local_path)
                shutil.copy2(local_path, backup_path)
                result.backed_up_files.append(str(backup_path))

    milestone_keys = [
        item.item_key for item in target_items if item.file_name == MILESTONES_FILE
    ]
    if milestone_keys:
        try:
            added = _merge_milestone_keys(milestone_keys)
            result.applied_count += added
            result.skipped_count += len(milestone_keys) - added
        except Exception as exc:
            result.errors.append(f"{MILESTONES_FILE}: {exc}")

    streak_paths = [
        item.item_key for item in target_items if item.file_name == STREAK_POLICIES_FILE
    ]
    if streak_paths:
        try:
            added = _merge_streak_paths(streak_paths)
            result.applied_count += added
            result.skipped_count += len(streak_paths) - added
        except Exception as exc:
            result.errors.append(f"{STREAK_POLICIES_FILE}: {exc}")

    last_names = [
        item.item_key for item in target_items if item.file_name == KOREAN_LAST_NAMES_FILE
    ]
    if last_names:
        try:
            added = _merge_korean_csv(
                KOREAN_LAST_NAMES_FILE,
                "last_name",
                last_names,
            )
            result.applied_count += added
            result.skipped_count += len(last_names) - added
        except Exception as exc:
            result.errors.append(f"{KOREAN_LAST_NAMES_FILE}: {exc}")

    first_names = [
        item.item_key
        for item in target_items
        if item.file_name == KOREAN_FIRST_NAMES_FILE
    ]
    if first_names:
        try:
            added = _merge_korean_csv(
                KOREAN_FIRST_NAMES_FILE,
                "first_name",
                first_names,
            )
            result.applied_count += added
            result.skipped_count += len(first_names) - added
        except Exception as exc:
            result.errors.append(f"{KOREAN_FIRST_NAMES_FILE}: {exc}")

    if result.applied_count and not result.errors:
        _mark_versions_applied(report.app_version)

    return result


def _mark_versions_applied(app_version: str) -> None:
    manifest = load_manifest()
    state = load_state()
    applied = {str(v) for v in state.get("applied_versions") or []}
    for release in manifest.get("releases") or []:
        release_version = str(release.get("app_version") or "").strip()
        if release_version and not _version_gt(release_version, app_version):
            applied.add(release_version)
    state["applied_versions"] = sorted(applied, key=_version_key)
    state["last_applied_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_applied_app_version"] = app_version
    save_state(state)


def _pending_milestone_items(
    app_version: str, spec: dict[str, Any]
) -> list[PendingBundleItem]:
    keys = [str(key) for key in spec.get("added_keys") or [] if str(key).strip()]
    if not keys:
        return []

    local_path = user_data_file_path(MILESTONES_FILE)
    if not local_path.is_file():
        local_keys: set[str] = set()
    else:
        local_defs = load_milestones(local_path)
        local_keys = {item.key for item in local_defs.all_milestones}

    bundle_path = bundle_data_path(MILESTONES_FILE)
    bundle_labels: dict[str, str] = {}
    if bundle_path.is_file():
        bundle_defs = load_milestones(bundle_path)
        bundle_labels = {item.key: item.label for item in bundle_defs.all_milestones}

    pending: list[PendingBundleItem] = []
    for key in keys:
        if key in local_keys:
            continue
        pending.append(
            PendingBundleItem(
                app_version=app_version,
                file_name=MILESTONES_FILE,
                item_key=key,
                label=bundle_labels.get(key, key),
            )
        )
    return pending


def _pending_streak_items(
    app_version: str, spec: dict[str, Any]
) -> list[PendingBundleItem]:
    paths = [str(path) for path in spec.get("added_paths") or [] if str(path).strip()]
    if not paths:
        return []

    local = _read_json(user_data_file_path(STREAK_POLICIES_FILE))
    bundle = _read_json(bundle_data_path(STREAK_POLICIES_FILE))

    pending: list[PendingBundleItem] = []
    for path in paths:
        if _get_nested(local, path) is not None:
            continue
        bundle_value = _get_nested(bundle, path)
        if bundle_value is None:
            continue
        pending.append(
            PendingBundleItem(
                app_version=app_version,
                file_name=STREAK_POLICIES_FILE,
                item_key=path,
                label=_streak_path_label(path, bundle),
            )
        )
    return pending


def _pending_korean_name_items(
    app_version: str,
    file_name: str,
    key_column: str,
    spec: dict[str, Any],
) -> list[PendingBundleItem]:
    names = [str(name) for name in spec.get("added_names") or [] if str(name).strip()]
    if not names:
        return []

    local_keys = _csv_key_set(user_data_file_path(file_name), key_column)
    bundle_rows = _csv_rows_by_key(bundle_data_path(file_name), key_column)

    pending: list[PendingBundleItem] = []
    for name in names:
        if name in local_keys:
            continue
        row = bundle_rows.get(name)
        if not row:
            continue
        korean = str(row.get("korean") or "").strip()
        pending.append(
            PendingBundleItem(
                app_version=app_version,
                file_name=file_name,
                item_key=name,
                label=f"{name} → {korean}" if korean else name,
            )
        )
    return pending


def _merge_milestone_keys(keys: list[str]) -> int:
    local_path = user_data_file_path(MILESTONES_FILE)
    bundle_path = bundle_data_path(MILESTONES_FILE)
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    local_defs = load_milestones(local_path) if local_path.is_file() else None
    bundle_defs = load_milestones(bundle_path)
    items = list(local_defs.all_milestones) if local_defs else []
    local_keys = {item.key for item in items}
    added = 0

    for milestone in bundle_defs.all_milestones:
        if milestone.key not in keys or milestone.key in local_keys:
            continue
        items.append(milestone)
        local_keys.add(milestone.key)
        added += 1

    save_milestones_csv(local_path, bundle_defs.with_milestones(items))
    return added


def _merge_streak_paths(paths: list[str]) -> int:
    local_path = user_data_file_path(STREAK_POLICIES_FILE)
    bundle_path = bundle_data_path(STREAK_POLICIES_FILE)
    local = _read_json(local_path)
    bundle = _read_json(bundle_path)
    added = 0

    for path in paths:
        if _get_nested(local, path) is not None:
            continue
        value = _get_nested(bundle, path)
        if value is None:
            continue
        _set_nested(local, path, value)
        added += 1

    _write_json(local_path, local)
    return added


def _merge_korean_csv(file_name: str, key_column: str, names: list[str]) -> int:
    local_path = user_data_file_path(file_name)
    bundle_path = bundle_data_path(file_name)
    local_rows = _read_csv_rows(local_path)
    bundle_rows = _read_csv_rows(bundle_path)
    local_keys = {str(row.get(key_column) or "").strip() for row in local_rows}
    fieldnames = _csv_fieldnames(local_path, bundle_path, key_column)
    added = 0

    for row in bundle_rows:
        key = str(row.get(key_column) or "").strip()
        if key not in names or key in local_keys:
            continue
        local_rows.append({name: row.get(name, "") for name in fieldnames})
        local_keys.add(key)
        added += 1

    _write_csv_rows(local_path, fieldnames, local_rows)
    return added


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _csv_key_set(path: Path, key_column: str) -> set[str]:
    return {
        str(row.get(key_column) or "").strip()
        for row in _read_csv_rows(path)
        if str(row.get(key_column) or "").strip()
    }


def _csv_rows_by_key(path: Path, key_column: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row in _read_csv_rows(path):
        key = str(row.get(key_column) or "").strip()
        if key:
            rows[key] = row
    return rows


def _csv_fieldnames(local_path: Path, bundle_path: Path, key_column: str) -> list[str]:
    for path in (local_path, bundle_path):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                return list(reader.fieldnames)
    return [key_column, "korean"]


def _get_nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _streak_path_label(path: str, bundle: dict[str, Any]) -> str:
    labels = bundle.get("labels") or {}
    streak_type = path.split(".")[-1]
    if path.startswith("labels."):
        return str(labels.get(streak_type, streak_type))
    label = labels.get(streak_type)
    if label:
        return label
    return path


def _backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}.bak.{stamp}{path.suffix}")


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _version_gt(left: str, right: str) -> bool:
    return _version_key(left) > _version_key(right)


def file_display_name(file_name: str) -> str:
    return tr(FILE_LABELS.get(file_name, file_name))


def pending_update_count() -> int:
    return scan_pending_updates().total


def apply_bundle_updates_with_message(parent=None) -> bool:
    """Merge pending bundle items and show a short result message."""
    from PyQt6.QtWidgets import QMessageBox

    report = scan_pending_updates()
    if not report.total:
        return False

    result = apply_pending_updates(report.items)
    if result.errors:
        QMessageBox.warning(parent, tr("Update Failed"), "\n".join(result.errors))
        return False

    QMessageBox.information(parent, tr("Reference File Update"), tr("Reference files merged successfully."))
    return True
