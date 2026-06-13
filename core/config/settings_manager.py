"""Application settings load/save and path resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core.config.paths import default_settings_path, resolve_data_path
from core.config.save_scanner import is_valid_league_folder
from core.stats.qualifiers import RatioQualifiers
from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    MLB_TEAM_ALIASES,
    merge_team_maps,
)


@dataclass
class AppSettings:
    ootp_version: int = 25
    current_season: int = 2024
    ootp_save_root: str = ""
    active_save: str = ""
    active_save_path: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    db_path: str = "data/records.db"
    milestones_path: str = "data/milestones.csv"
    import_state: dict[str, str] = field(default_factory=dict)
    initial_stats_dir: str = ""
    tracked_teams: list[str] = field(default_factory=list)
    custom_mlb_teams: dict[str, str] = field(default_factory=dict)
    import_mlb_only: bool = True
    season_games_total: int = 162
    ratio_qualifiers: dict[str, float] = field(
        default_factory=lambda: {
            "batting_ab_per_game": 3.1,
            "pitching_ip_per_game": 1.0,
        }
    )

    @property
    def boxscore_dir(self) -> str:
        if self.paths.get("boxscore_dir"):
            return self.paths["boxscore_dir"]
        if self.active_save_path:
            return str(Path(self.active_save_path) / "news" / "html" / "box_scores")
        return ""

    @property
    def game_logs_dir(self) -> str:
        if self.paths.get("game_logs_dir"):
            return self.paths["game_logs_dir"]
        if self.active_save_path:
            return str(Path(self.active_save_path) / "news" / "html" / "game_logs")
        return ""

    @property
    def import_export_dir(self) -> str:
        if self.paths.get("import_export_dir"):
            return self.paths["import_export_dir"]
        if self.active_save_path:
            return str(Path(self.active_save_path) / "import_export")
        return ""

    @property
    def roster_file(self) -> str:
        if self.paths.get("roster_file"):
            return self.paths["roster_file"]
        return ""

    def team_name_map(self) -> dict[str, str]:
        return merge_team_maps(
            CANONICAL_MLB_TEAMS, MLB_TEAM_ALIASES, self.custom_mlb_teams
        )

    def get_ratio_qualifiers(self) -> RatioQualifiers:
        raw = self.ratio_qualifiers or {}
        return RatioQualifiers(
            batting_ab_per_game=float(raw.get("batting_ab_per_game", 3.1)),
            pitching_ip_per_game=float(raw.get("pitching_ip_per_game", 1.0)),
        )


class SettingsManager:
    """Load, validate, and persist application settings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_settings_path()

    def load(self) -> AppSettings:
        if not self.path.exists():
            example = self.path.with_suffix(".json.example")
            if example.exists():
                settings = self._parse_json(example.read_text(encoding="utf-8"))
            else:
                settings = AppSettings()
        else:
            settings = self._parse_json(self.path.read_text(encoding="utf-8"))

        return self.ensure_derived_paths(settings)

    def ensure_derived_paths(self, settings: AppSettings) -> AppSettings:
        """Fill paths from active_save_path when missing (persist on next save)."""
        if not settings.active_save_path:
            return settings
        settings.paths = self._derive_paths(settings.active_save_path, settings.paths)
        if not settings.initial_stats_dir:
            settings.initial_stats_dir = str(
                Path(settings.active_save_path) / "import_export"
            )
        return settings

    def save(self, settings: AppSettings) -> None:
        settings = self.ensure_derived_paths(settings)
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
            "import_state": dict(settings.import_state),
            "initial_stats_dir": settings.initial_stats_dir,
            "tracked_teams": list(settings.tracked_teams),
            "custom_mlb_teams": dict(settings.custom_mlb_teams),
            "import_mlb_only": settings.import_mlb_only,
            "season_games_total": settings.season_games_total,
            "ratio_qualifiers": dict(settings.ratio_qualifiers),
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
        settings.initial_stats_dir = str(Path(save_path) / "import_export")
        return settings

    @staticmethod
    def _derive_paths(save_path: str, existing: dict[str, str]) -> dict[str, str]:
        league = Path(save_path)
        derived = dict(existing)
        derived["boxscore_dir"] = str(league / "news" / "html" / "box_scores")
        derived["game_logs_dir"] = str(league / "news" / "html" / "game_logs")
        derived["import_export_dir"] = str(league / "import_export")
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
            milestones_path=str(raw.get("milestones_path", "data/milestones.csv")),
            import_state=dict(raw.get("import_state", {})),
            initial_stats_dir=str(raw.get("initial_stats_dir", "")),
            tracked_teams=[
                str(team).strip().upper()
                for team in raw.get("tracked_teams", [])
                if str(team).strip()
            ],
            custom_mlb_teams={
                str(abbr).strip().upper(): str(name).strip()
                for abbr, name in raw.get("custom_mlb_teams", {}).items()
                if str(abbr).strip() and str(name).strip()
            },
            import_mlb_only=bool(raw.get("import_mlb_only", True)),
            season_games_total=int(raw.get("season_games_total", 162)),
            ratio_qualifiers=dict(
                raw.get(
                    "ratio_qualifiers",
                    {"batting_ab_per_game": 3.1, "pitching_ip_per_game": 1.0},
                )
            ),
        )

    def get_last_boxscore_import_at(self, settings: AppSettings, boxscore_dir: str) -> float | None:
        """Return last import epoch for a boxscore directory, if recorded."""
        state_dir = settings.import_state.get("boxscore_dir", "")
        if state_dir != str(Path(boxscore_dir).resolve()):
            return None
        raw = settings.import_state.get("last_import_at")
        if not raw:
            return None
        try:
            from datetime import datetime

            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            return None

    def update_boxscore_import_timestamp(
        self, settings: AppSettings, boxscore_dir: str
    ) -> AppSettings:
        from datetime import datetime, timezone

        settings.import_state = {
            "boxscore_dir": str(Path(boxscore_dir).resolve()),
            "last_import_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return settings


def load_settings(path: str | Path | None = None) -> AppSettings:
    return SettingsManager(path).load()
