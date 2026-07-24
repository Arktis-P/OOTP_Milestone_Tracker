"""QThread worker for validation-only season replay."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.validation.season_replay import ReplayConfig, run_season_replay


class SeasonValidationWorker(QThread):
    """Run season replay against a validation DB so the GUI stays responsive."""

    completed = pyqtSignal(dict, str)
    error = pyqtSignal(str)

    def __init__(self, config: ReplayConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        try:
            report = run_season_replay(self.config).to_dict()
            report_path = Path(self.config.target_db).with_name("replay_report.json")
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.error.emit(str(exc))
            return
        self.completed.emit(report, str(report_path))
