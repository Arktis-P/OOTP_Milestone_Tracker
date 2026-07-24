"""Background workers for data import."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import logging
from pathlib import Path
import time

from PyQt6.QtCore import QThread, pyqtSignal

from core.import_workflow import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL_SUCCESS,
)
from core.config.settings_manager import AppSettings, SettingsManager
from core.db.meta import get_meta, set_meta
from core.milestone.checker import MilestoneAchievement, MilestoneChecker
from core.milestone.prediction_store import PredictionStore
from core.milestone.definitions import MilestoneDefinitions
from core.i18n import tr
from core.roster.korean_names import note_players_from_boxscore_import
from core.streak.tracker import StreakTracker
from core.stats.aggregator import Aggregator
from core.stats.aggregator import ImportCancelled
from core.stats.models import BatchImportResult, ImportResult


BATTING_NOTES_MULTI_INNING_META = "batting_notes_multi_inning_v1"
logger = logging.getLogger(__name__)


@dataclass
class ImportFinishedPayload:
    batch: BatchImportResult
    milestones: list[MilestoneAchievement] = field(default_factory=list)
    milestones_recorded: int = 0
    outcome: str = OUTCOME_COMPLETED
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    excluded: int = 0
    errors: int = 0
    unresolved: dict[str, int] = field(default_factory=dict)
    message: str = ""

    @classmethod
    def from_batch(
        cls,
        batch: BatchImportResult,
        *,
        milestones: list[MilestoneAchievement] | None = None,
        milestones_recorded: int = 0,
        outcome: str | None = None,
        message: str = "",
    ) -> "ImportFinishedPayload":
        milestones = milestones or []
        errors = len(batch.errors)
        processed = batch.total_scanned or batch.candidates or (
            batch.imported
            + batch.skipped
            + batch.skipped_mtime
            + batch.skipped_existing
            + batch.skipped_non_mlb
            + batch.skipped_spring_training
            + batch.deferred_changed
            + errors
        )
        created = batch.imported + milestones_recorded
        duplicates = batch.skipped_existing
        excluded = batch.skipped_non_mlb + batch.skipped_spring_training
        unresolved = {"errors": errors} if errors else {}
        if batch.deferred_changed:
            unresolved["deferred_changed"] = batch.deferred_changed

        if outcome is None:
            success_count = batch.imported + len(batch.refreshed_game_ids) + milestones_recorded
            if errors:
                outcome = OUTCOME_PARTIAL_SUCCESS if success_count else OUTCOME_FAILED
            else:
                outcome = OUTCOME_COMPLETED

        if not message:
            message = _build_completion_message(
                outcome=outcome,
                processed=processed,
                created=created,
                duplicates=duplicates,
                excluded=excluded,
                errors=errors,
            )

        return cls(
            batch=batch,
            milestones=milestones,
            milestones_recorded=milestones_recorded,
            outcome=outcome,
            processed=processed,
            created=created,
            duplicates=duplicates,
            excluded=excluded,
            errors=errors,
            unresolved=unresolved,
            message=message,
        )


def _build_completion_message(
    *,
    outcome: str,
    processed: int,
    created: int,
    duplicates: int,
    excluded: int,
    errors: int,
) -> str:
    parts = [
        tr("{count} processed").format(count=processed),
        tr("{count} created").format(count=created),
    ]
    if duplicates:
        parts.append(tr("{count} duplicates").format(count=duplicates))
    if excluded:
        parts.append(tr("{count} excluded").format(count=excluded))
    if errors:
        parts.append(tr("{count} errors").format(count=errors))
    prefix = {
        OUTCOME_COMPLETED: tr("Import Complete"),
        OUTCOME_PARTIAL_SUCCESS: tr("Import Partially Complete"),
        OUTCOME_FAILED: tr("Import Failed"),
        OUTCOME_CANCELLED: tr("Import Cancelled"),
    }.get(outcome, tr("Import Result"))
    return prefix + " · " + " · ".join(parts)


class ImportWorker(QThread):
    """Import box scores on a worker thread with its own SQLite connection."""

    # Keep QThread.finished intact for lifecycle cleanup after ``run`` has
    # returned.  This payload signal is emitted just before that point.
    workflow_finished = pyqtSignal(object)
    completed = pyqtSignal(object)
    cancelled = pyqtSignal(str)
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
        self._last_batch_result: BatchImportResult | None = None

    def cancel(self) -> None:
        """Request cooperative cancellation at the next game/file boundary."""
        self.requestInterruption()

    def _raise_if_cancelled(self, _current: int, _total: int, _name: str) -> None:
        if self.isInterruptionRequested():
            raise ImportCancelled("Import cancelled by user.")

    def run(self) -> None:
        try:
            started = time.monotonic()
            logger.debug(
                "import_worker_start season=%s directory=%s", self.season, self.boxscore_dir
            )
            with Aggregator(self.db_path) as aggregator:
                result = aggregator.import_all_new(
                    self.boxscore_dir,
                    self.season,
                    since_mtime=self.since_mtime,
                    mlb_only=self.settings.import_mlb_only,
                    progress_callback=lambda cur, total, name: self.progress.emit(
                        cur, total, name, "import"
                    ),
                    should_cancel=self.isInterruptionRequested,
                    commit=False,
                )
                self._last_batch_result = result
                self._raise_if_cancelled(0, 1, "raw import")
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
                        source_snapshot=result.source_snapshot,
                        progress_callback=lambda cur, total, name: self.progress.emit(
                            cur, total, name, "backfill"
                        ),
                        should_cancel=self.isInterruptionRequested,
                        commit=False,
                    )
                    game_ids_for_milestones.extend(backfilled)
                    set_meta(
                        aggregator.conn, BATTING_NOTES_MULTI_INNING_META, "1"
                    )
                game_ids_for_milestones = sorted(set(game_ids_for_milestones))
                logger.debug(
                    "import_worker_games_ready season=%s games=%s imported=%s refreshed=%s",
                    self.season,
                    len(game_ids_for_milestones),
                    result.imported,
                    len(result.refreshed_game_ids),
                )
                checker = MilestoneChecker(
                    aggregator,
                    self.milestones,
                    season_games_total=self.settings.season_games_total,
                    ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                    tracked_teams=self.settings.tracked_teams,
                    custom_teams=self.settings.custom_mlb_teams,
                )
                achievements: list[MilestoneAchievement] = []
                recorded = 0
                if game_ids_for_milestones:
                    logger.debug("import_worker_milestone_start season=%s games=%s", self.season, len(game_ids_for_milestones))
                    achievements = checker.check_new_games(
                        game_ids_for_milestones,
                        self.season,
                        progress_callback=lambda cur, total, name: (
                            self._raise_if_cancelled(cur, total, name),
                            self.progress.emit(cur, total, name, "milestone"),
                        )[-1],
                    )
                    recorded = checker.record_achievements(
                        achievements,
                        game_logs_dir=self.settings.game_logs_dir or None,
                        commit=False,
                    )
                    logger.debug("import_worker_milestone_finish season=%s achievements=%s recorded=%s", self.season, len(achievements), recorded)

                streak_recorded = 0
                if game_ids_for_milestones:
                    logger.debug("import_worker_streak_start season=%s games=%s", self.season, len(game_ids_for_milestones))
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
                        should_cancel=self.isInterruptionRequested,
                        commit_events=False,
                    )
                    streak_recorded = len(streak_events)
                    logger.debug("import_worker_streak_finish season=%s events=%s", self.season, streak_recorded)
                # Raw games, processed-file metadata, milestones, and streak
                # state now share a single owner commit.  A cancellation or
                # error above leaves the context manager to roll everything
                # back, so a later import cannot see half-processed games.
                self._raise_if_cancelled(1, 1, "derived records")
                aggregator.conn.commit()
                logger.debug(
                    "import_worker_commit season=%s games=%s elapsed_s=%.3f",
                    self.season,
                    len(game_ids_for_milestones),
                    time.monotonic() - started,
                )

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

            payload = ImportFinishedPayload.from_batch(
                result,
                milestones=achievements,
                milestones_recorded=recorded,
            )
            self.workflow_finished.emit(payload)
            self.completed.emit(payload)
            logger.debug(
                "import_worker_finish season=%s elapsed_s=%.3f",
                self.season,
                time.monotonic() - started,
            )
        except ImportCancelled as exc:
            logger.debug("import_worker_cancelled season=%s reason=%s", self.season, exc)
            payload = ImportFinishedPayload.from_batch(
                self._last_batch_result or BatchImportResult(),
                outcome=OUTCOME_CANCELLED,
                message=str(exc),
            )
            payload = replace(payload, created=0)
            self.workflow_finished.emit(payload)
            self.cancelled.emit(str(exc))
        except Exception as exc:
            batch = self._last_batch_result or BatchImportResult()
            if not batch.errors:
                batch.errors.append(ImportResult(game_id=0, error=str(exc)))
            payload = ImportFinishedPayload.from_batch(
                batch,
                outcome=OUTCOME_FAILED,
                message=str(exc),
            )
            payload = replace(payload, created=0)
            self.workflow_finished.emit(payload)
            self.error.emit(str(exc))
