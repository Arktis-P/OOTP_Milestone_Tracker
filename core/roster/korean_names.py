"""Load roman → Korean name parts from data/korean_*_names.csv."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from core.config import resolve_data_path

DEFAULT_LAST_NAMES_FILE = "data/korean_last_names.csv"
DEFAULT_FIRST_NAMES_FILE = "data/korean_first_names.csv"


@dataclass
class KoreanNameMapper:
    """Maps OOTP LastName / FirstName strings to Korean display text."""

    last_names: dict[str, str] = field(default_factory=dict)
    first_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> KoreanNameMapper:
        if data_dir is not None:
            base = Path(data_dir)
            last_path = base / "korean_last_names.csv"
            first_path = base / "korean_first_names.csv"
        else:
            last_path = resolve_data_path(DEFAULT_LAST_NAMES_FILE)
            first_path = resolve_data_path(DEFAULT_FIRST_NAMES_FILE)
        return cls(
            last_names=_load_part_csv(last_path, "last_name"),
            first_names=_load_part_csv(first_path, "first_name"),
        )

    def korean_last(self, last_name: str) -> str:
        return self.last_names.get(last_name.strip(), "")

    def korean_first(self, first_name: str) -> str:
        return self.first_names.get(first_name.strip(), "")

    def format_player_name(self, last_name: str, first_name: str) -> str:
        """Return Korean full name (성+이름) when mappings exist."""
        kr_last = self.korean_last(last_name)
        kr_first = self.korean_first(first_name)
        if kr_last and kr_first:
            return f"{kr_last}{kr_first}"
        if kr_last:
            return kr_last
        if kr_first:
            return kr_first
        return ""


def _load_part_csv(path: Path, key_column: str) -> dict[str, str]:
    if not path.is_file():
        return {}
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or key_column not in reader.fieldnames:
            return {}
        for row in reader:
            key = (row.get(key_column) or "").strip()
            value = (row.get("korean") or "").strip()
            if key and value:
                mapping[key] = value
    return mapping
