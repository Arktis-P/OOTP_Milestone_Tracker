"""Background worker for initial stats import."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.stats.aggregator import Aggregator
from core.stats.initial_import import ImportMode, InitialImporter, InitImportResult


class InitialImportWorker(QThread):
    """Run initial import on a worker thread with its own SQLite connection."""

    completed = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)
    discovered_teams = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: str | Path,
        *,
        batting_path: str | None,
        pitching_path: str | None,
        mode: ImportMode,
        current_season: int,
        persist: bool,
        known_teams: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.batting_path = batting_path
        self.pitching_path = pitching_path
        self.mode = mode
        self.current_season = current_season
        self.persist = persist
        self.known_teams = dict(known_teams or {})

    def run(self) -> None:
        try:
            if self.persist:
                results = self._run_against(self.db_path)
            else:
                # Preview imports also synchronize roster/team tables. Run them
                # against a database snapshot so declining or failing a preview
                # can never modify the user's live database.
                with tempfile.TemporaryDirectory(
                    prefix="ootp-init-preview-", dir=self.db_path.parent
                ) as tmp:
                    preview_db = Path(tmp) / "preview.db"
                    self._snapshot_database(preview_db)
                    results = self._run_against(preview_db)
            self.completed.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))

    def _snapshot_database(self, destination: Path) -> None:
        with closing(sqlite3.connect(self.db_path)) as source, closing(
            sqlite3.connect(destination)
        ) as target:
            source.backup(target)

    def _run_against(self, db_path: Path) -> list[InitImportResult]:
        with Aggregator(db_path) as aggregator:
            importer = InitialImporter(aggregator)
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
                results.append(fn(path, self.mode, self.current_season, persist=self.persist))
            if not self.persist:
                unknown = importer.discover_unknown_mlb_teams(
                    self.batting_path,
                    self.pitching_path,
                    self.known_teams,
                )
                self.discovered_teams.emit(unknown)
        return results
