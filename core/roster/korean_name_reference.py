"""Curated MLB/KBO roman → Hangul reference loaded from bundled + user CSVs."""

from __future__ import annotations

import csv
from pathlib import Path

from core.config.paths import ensure_user_data_dir, get_bundle_root

ReferenceMaps = tuple[dict[str, str], dict[str, str]]

_cache: dict[str, ReferenceMaps] = {}


def clear_reference_cache() -> None:
    _cache.clear()


def load_merged_reference(data_dir: str | Path | None = None) -> ReferenceMaps:
    """Merge filled rows from bundle defaults and user CSV (user wins on conflict)."""
    last_names: dict[str, str] = {}
    first_names: dict[str, str] = {}

    bundle_dir = get_bundle_root() / "data"
    user_dir = Path(data_dir) if data_dir is not None else ensure_user_data_dir()

    for directory in (bundle_dir, user_dir):
        _merge_part_file(directory / "korean_last_names.csv", "last_name", last_names)
        _merge_part_file(directory / "korean_first_names.csv", "first_name", first_names)

    return last_names, first_names


def get_reference(data_dir: str | Path | None = None) -> ReferenceMaps:
    key = str(Path(data_dir) if data_dir is not None else ensure_user_data_dir())
    if key not in _cache:
        _cache[key] = load_merged_reference(data_dir)
    return _cache[key]


def lookup_reference(part: str, name: str, *, data_dir: str | Path | None = None) -> str:
    table = get_reference(data_dir)[0 if part == "last" else 1]
    return table.get(name.strip(), "")


def lookup_reference_ci(part: str, name: str, *, data_dir: str | Path | None = None) -> str:
    needle = name.strip().casefold()
    if not needle:
        return ""
    table = get_reference(data_dir)[0 if part == "last" else 1]
    for key, value in table.items():
        if key.casefold() == needle:
            return value
    return ""


def _merge_part_file(path: Path, key_column: str, target: dict[str, str]) -> None:
    if not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or key_column not in reader.fieldnames:
            return
        for row in reader:
            key = (row.get(key_column) or "").strip()
            value = (row.get("korean") or "").strip()
            if key and value:
                target[key] = value
