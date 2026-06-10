"""Application configuration loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppSettings:
    ootp_version: int = 25
    current_season: int = 2024
    paths: dict[str, str] = field(default_factory=dict)
    db_path: str = "data/records.db"
    milestones_path: str = "data/milestones.json"

    @property
    def boxscore_dir(self) -> str:
        return self.paths.get("boxscore_dir", "")

    @property
    def roster_file(self) -> str:
        return self.paths.get("roster_file", "")


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_data_path(relative: str) -> Path:
    return get_project_root() / relative


def load_settings(path: str | Path | None = None) -> AppSettings:
    settings_path = Path(path) if path else resolve_data_path("data/settings.json")
    if not settings_path.exists():
        example = settings_path.with_suffix(".json.example")
        if example.exists():
            settings_path = example
        else:
            return AppSettings()

    with settings_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    return AppSettings(
        ootp_version=int(raw.get("ootp_version", 25)),
        current_season=int(raw.get("current_season", 2024)),
        paths=dict(raw.get("paths", {})),
        db_path=str(raw.get("db_path", "data/records.db")),
        milestones_path=str(raw.get("milestones_path", "data/milestones.json")),
    )
