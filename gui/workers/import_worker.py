"""Background workers for data import."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.config.settings_manager import AppSettings, SettingsManager
from core.db.meta import get_meta, set_meta
from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.prediction_store import PredictionStore
from core.milestone.definitions import MilestoneDefinitions
from core.i18n import tr
from core.roster.korean_names import note_players_from_boxscore_import
from core.streak.tracker import StreakTracker
from core.stats.aggregator import Aggregator
from core.stats.models import BatchImportResult


BATTING_NOTES_MULTI_INNING_META = "batting_notes_multi_inning_v1"


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
                game_ids_for_milestones = list(result.imported_game_ids)
                game_ids_for_milestones.extend(result.refreshed_game_ids)
                if (
                    get_meta(aggregator.conn, BATTING_NOTES_MULTI_INNING_META) != "1"
                    and self.boxscore_dir
                ):
                    self.progress.emit(0, 1, tr("Re-parsing BATTING notes"), "import")
                    backfilled = aggregator.refresh_all_batting_events_from_dir(
                        self.boxscore_dir,
                        self.season,
                        mlb_only=self.settings.import_mlb_only,
                    )
                    game_ids_for_milestones.extend(backfilled)
                    set_meta(
                        aggregator.conn, BATTING_NOTES_MULTI_INNING_META, "1"
                    )
                game_ids_for_milestones = sorted(set(game_ids_for_milestones))
                checker = MilestoneChecker(
                    aggregator,
                    self.milestones,
                    season_games_total=self.settings.season_games_total,
                    ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                    tracked_teams=self.settings.tracked_teams,
                    custom_teams=self.settings.custom_mlb_teams,
                )
                achievements: list[MilestoneAchievement] = []
                if game_ids_for_milestones:
                    achievements = checker.check_new_games(
                        game_ids_for_milestones,
                        self.season,
                        progress_callback=lambda cur, total, name: self.progress.emit(
                            cur, total, name, "milestone"
                        ),
                    )
                recorded = checker.record_achievements(
                    achievements,
                    game_logs_dir=self.settings.game_logs_dir or None,
                )

                streak_recorded = 0
                if game_ids_for_milestones:
                    streak_tracker = StreakTracker(
                        aggregator,
                        tracked_teams=self.settings.tracked_teams,
                        custom_teams=self.settings.custom_mlb_teams,
                    )
                    streak_events = streak_tracker.process_new_games(
                        game_ids_for_milestones,
                        self.season,
                        progress_callback=lambda cur, total, name: self.progress.emit(
                            cur, total, name, "streak"
                        ),
                    )
                    streak_recorded = len(streak_events)
                    aggregator.conn.commit()

                if game_ids_for_milestones:
                    PredictionStore(
                        aggregator,
                        self.milestones,
                        season=self.season,
                        season_games_total=self.settings.season_games_total,
                        tracked_teams=self.settings.tracked_teams,
                        custom_teams=self.settings.custom_mlb_teams,
                    ).update_after_import(game_ids_for_milestones)
                    note_players_from_boxscore_import(
                        aggregator,
                        game_ids_for_milestones,
                        import_export_dir=(
                            self.settings.import_export_dir
                            or self.settings.initial_stats_dir
                        ),
                    )

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
