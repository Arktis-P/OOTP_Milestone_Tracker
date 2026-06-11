"""Application settings load/save and path resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core.config.save_scanner import is_valid_league_folder


@dataclass
class AppSettings:
    ootp_version: int = 25
    current_season: int = 2024
    ootp_save_root: str = ""
    active_save: str = ""
    active_save_path: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    db_path: str = "data/records.db"
    milestones_path: str = "data/milestones.json"

    @property
    def boxscore_dir(self) -> str:
        if self.paths.get("boxscore_dir"):
            return self.paths["boxscore_dir"]
        if self.active_save_path:
            return str(Path(self.active_save_path) / "news" / "html" / "box_scores")
        return ""

    @property
    def roster_file(self) -> str:
        if self.paths.get("roster_file"):
            return self.paths["roster_file"]
        return ""


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def resolve_data_path(relative: str) -> Path:
    return get_project_root() / relative


def default_settings_path() -> Path:
    return resolve_data_path("data/settings.json")


class SettingsManager:
    """Load, validate, and persist application settings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_settings_path()

    def load(self) -> AppSettings:
        if not self.path.exists():
            example = self.path.with_suffix(".json.example")
            if example.exists():
                return self._parse_json(example.read_text(encoding="utf-8"))
            return AppSettings()

        return self._parse_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ootp_version": settings.ootp_version,
            "current_season": settings.current_season,
            "ootp_save_root": settings.ootp_save_root,
            "active_save": settings.active_save,
            "active_save_path": settings.active_save_path,
            "paths": dict(settings.paths),
            "db_path": settings.db_path,
            "milestones_path": settings.milestones_path,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def is_active_save_valid(self, settings: AppSettings | None = None) -> bool:
        settings = settings or self.load()
        if not settings.active_save_path:
            return False
        return is_valid_league_folder(settings.active_save_path)

    def is_setup_complete(self) -> bool:
        return self.is_active_save_valid()

    def update_active_save(
        self,
        settings: AppSettings,
        *,
        save_root: str,
        save_name: str,
        save_path: str,
        ootp_version: int | None = None,
    ) -> AppSettings:
        settings.ootp_save_root = save_root
        settings.active_save = save_name
        settings.active_save_path = save_path
        if ootp_version is not None:
            settings.ootp_version = ootp_version
        settings.paths = self._derive_paths(save_path, settings.paths)
        return settings

    @staticmethod
    def _derive_paths(save_path: str, existing: dict[str, str]) -> dict[str, str]:
        league = Path(save_path)
        derived = dict(existing)
        derived["boxscore_dir"] = str(league / "news" / "html" / "box_scores")
        derived.setdefault("roster_file", "")
        return derived

    @staticmethod
    def _parse_json(raw_text: str) -> AppSettings:
        raw = json.loads(raw_text)
        return AppSettings(
            ootp_version=int(raw.get("ootp_version", 25)),
            current_season=int(raw.get("current_season", 2024)),
            ootp_save_root=str(raw.get("ootp_save_root", "")),
            active_save=str(raw.get("active_save", "")),
            active_save_path=str(raw.get("active_save_path", "")),
            paths=dict(raw.get("paths", {})),
            db_path=str(raw.get("db_path", "data/records.db")),
            milestones_path=str(raw.get("milestones_path", "data/milestones.json")),
        )


def load_settings(path: str | Path | None = None) -> AppSettings:
    return SettingsManager(path).load()
