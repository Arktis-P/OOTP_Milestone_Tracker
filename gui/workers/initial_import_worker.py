"""Background worker for initial stats import."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.stats.aggregator import Aggregator
from core.stats.initial_import import ImportMode, InitialImporter, InitImportResult


class InitialImportWorker(QThread):
    finished = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)
    error = pyqtSignal(str)

    def __init__(
        self,
        aggregator: Aggregator,
        *,
        batting_path: str | None,
        pitching_path: str | None,
        mode: ImportMode,
        current_season: int,
        persist: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.batting_path = batting_path
        self.pitching_path = pitching_path
        self.mode = mode
        self.current_season = current_season
        self.persist = persist

    def run(self) -> None:
        try:
            importer = InitialImporter(self.aggregator)
            results: list[InitImportResult] = []
            tasks: list[tuple[str, str | Path, str]] = []
            if self.batting_path:
                tasks.append(("batting", self.batting_path, "player_batting_stats.txt"))
            if self.pitching_path:
                tasks.append(("pitching", self.pitching_path, "player_pitching_stats.txt"))
            total = len(tasks)
            for index, (kind, path, label) in enumerate(tasks, start=1):
                self.progress.emit(index, total, label)
                fn = importer.import_batting if kind == "batting" else importer.import_pitching
                results.append(
                    fn(path, self.mode, self.current_season, persist=self.persist)
                )
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
