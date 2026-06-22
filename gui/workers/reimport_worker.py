"""Background worker for dev single-boxscore re-import."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.config.settings_manager import AppSettings, SettingsManager
from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import PredictionStore
from core.roster.korean_names import note_players_from_boxscore_import
from core.streak.tracker import StreakTracker
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.models import BatchImportResult, ImportResult
from gui.workers.import_worker import ImportFinishedPayload


class ReimportBoxscoreWorker(QThread):
    """Re-import one box score file (replace existing data if present)."""

    finished = pyqtSignal(object)
    progress = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: str | Path,
        settings_manager: SettingsManager,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        filepath: str | Path,
        season: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.settings_manager = settings_manager
        self.milestones = milestones
        self.settings = settings
        self.filepath = Path(filepath)
        self.season = season

    def run(self) -> None:
        try:
            filename = self.filepath.name
            self.progress.emit(tr("Re-importing boxscore: {filename}").format(filename=filename))

            with Aggregator(self.db_path) as aggregator:
                import_result = aggregator.reimport_boxscore_file(
                    self.filepath,
                    self.season,
                    mlb_only=self.settings.import_mlb_only,
                )

                batch = BatchImportResult(total_scanned=1, candidates=1)
                if import_result.error:
                    batch.errors.append(import_result)
                elif import_result.skipped:
                    batch.skipped = 1
                else:
                    batch.imported = 1
                    batch.imported_game_ids.append(import_result.game_id)

                achievements: list[MilestoneAchievement] = []
                recorded = 0
                if batch.imported_game_ids:
                    self.progress.emit(tr("Checking milestones..."))
                    checker = MilestoneChecker(
                        aggregator,
                        self.milestones,
                        season_games_total=self.settings.season_games_total,
                        ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                        tracked_teams=self.settings.tracked_teams,
                        custom_teams=self.settings.custom_mlb_teams,
                    )
                    achievements = checker.check_new_games(
                        batch.imported_game_ids,
                        self.season,
                    )
                    recorded = checker.record_achievements(
                        achievements,
                        game_logs_dir=self.settings.game_logs_dir or None,
                    )

                    self.progress.emit(tr("Processing streak records..."))
                    streak_tracker = StreakTracker(
                        aggregator,
                        tracked_teams=self.settings.tracked_teams,
                        custom_teams=self.settings.custom_mlb_teams,
                    )
                    streak_tracker.process_new_games(
                        batch.imported_game_ids,
                        self.season,
                    )
                    aggregator.conn.commit()

                    self.progress.emit(tr("Updating prediction list..."))
                    PredictionStore(
                        aggregator,
                        self.milestones,
                        season=self.season,
                        season_games_total=self.settings.season_games_total,
                        tracked_teams=self.settings.tracked_teams,
                        custom_teams=self.settings.custom_mlb_teams,
                    ).update_after_import(batch.imported_game_ids)
                    if self.settings.import_mlb_only:
                        note_players_from_boxscore_import(
                            aggregator,
                            batch.imported_game_ids,
                            import_export_dir=(
                                self.settings.import_export_dir
                                or self.settings.initial_stats_dir
                            ),
                        )

            self.finished.emit(
                ImportFinishedPayload(
                    batch=batch,
                    milestones=achievements,
                    milestones_recorded=recorded,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))
