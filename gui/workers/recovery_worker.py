"""Background worker for the spring-training/regular-season recovery scan."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.stats.aggregator import Aggregator


class RecoverRegularSeasonWorker(QThread):
    """Runs Aggregator.recover_regular_season_after_spring_training off the UI thread.

    This scan stats and parses every box score file at or after the most
    recent spring-training file's mtime, which can take a while over a large
    or cloud-synced (e.g. OneDrive) box score folder.
    """

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, db_path: str | Path, boxscore_dir: str, season: int, parent=None) -> None:
        super().__init__(parent)
        self.db_path = db_path
        self.boxscore_dir = boxscore_dir
        self.season = season

    def run(self) -> None:
        try:
            with Aggregator(self.db_path) as aggregator:
                report = aggregator.recover_regular_season_after_spring_training(
                    self.boxscore_dir, self.season, mlb_only=True
                )
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))
