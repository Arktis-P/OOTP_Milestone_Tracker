"""Background workers for data import."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.config.settings_manager import SettingsManager
from core.stats.aggregator import Aggregator
from core.stats.models import BatchImportResult


class ImportWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        aggregator: Aggregator,
        settings_manager: SettingsManager,
        boxscore_dir: str,
        season: int,
        since_mtime: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings_manager = settings_manager
        self.boxscore_dir = boxscore_dir
        self.season = season
        self.since_mtime = since_mtime

    def run(self) -> None:
        try:
            result = self.aggregator.import_all_new(
                self.boxscore_dir,
                self.season,
                since_mtime=self.since_mtime,
            )
            settings = self.settings_manager.load()
            updated = self.settings_manager.update_boxscore_import_timestamp(
                settings, self.boxscore_dir
            )
            self.settings_manager.save(updated)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
