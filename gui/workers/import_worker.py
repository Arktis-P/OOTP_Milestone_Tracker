"""Background workers for data import."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.config.settings_manager import AppSettings, SettingsManager
from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.prediction_store import PredictionStore
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.models import BatchImportResult


@dataclass
class ImportFinishedPayload:
    batch: BatchImportResult
    milestones: list[MilestoneAchievement] = field(default_factory=list)
    milestones_recorded: int = 0


class ImportWorker(QThread):
    """Import box scores on a worker thread with its own SQLite connection."""

    finished = pyqtSignal(object)
    progress = pyqtSignal(int, int, str, str)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: str | Path,
        settings_manager: SettingsManager,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        boxscore_dir: str,
        season: int,
        since_mtime: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.settings_manager = settings_manager
        self.milestones = milestones
        self.settings = settings
        self.boxscore_dir = boxscore_dir
        self.season = season
        self.since_mtime = since_mtime

    def run(self) -> None:
        try:
            with Aggregator(self.db_path) as aggregator:
                result = aggregator.import_all_new(
                    self.boxscore_dir,
                    self.season,
                    since_mtime=self.since_mtime,
                    mlb_only=self.settings.import_mlb_only,
                    progress_callback=lambda cur, total, name: self.progress.emit(
                        cur, total, name, "import"
                    ),
                )
                checker = MilestoneChecker(
                    aggregator,
                    self.milestones,
                    season_games_total=self.settings.season_games_total,
                    ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                )
                achievements: list[MilestoneAchievement] = []
                if result.imported_game_ids:
                    achievements = checker.check_new_games(
                        result.imported_game_ids,
                        self.season,
                        progress_callback=lambda cur, total, name: self.progress.emit(
                            cur, total, name, "milestone"
                        ),
                    )
                recorded = checker.record_achievements(achievements)

                if result.imported_game_ids:
                    PredictionStore(
                        aggregator,
                        self.milestones,
                        season=self.season,
                        season_games_total=self.settings.season_games_total,
                        tracked_teams=self.settings.tracked_teams,
                    ).update_after_import(result.imported_game_ids)

            settings = self.settings_manager.load()
            updated = self.settings_manager.update_boxscore_import_timestamp(
                settings, self.boxscore_dir
            )
            self.settings_manager.save(updated)

            self.finished.emit(
                ImportFinishedPayload(
                    batch=result,
                    milestones=achievements,
                    milestones_recorded=recorded,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))
