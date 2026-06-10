"""QApplication root and main window."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QStatusBar, QTabWidget

from core.config import load_settings, resolve_data_path
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from gui.views.milestone_view import MilestoneView
from gui.views.predict_view import PredictView
from gui.views.roster_view import RosterView
from gui.views.stats_view import StatsView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OOTP Milestone Tracker")
        self.resize(1100, 720)

        self.settings = load_settings()
        self.aggregator = Aggregator(resolve_data_path(self.settings.db_path))
        self.milestones = load_milestones(
            resolve_data_path(self.settings.milestones_path)
        )

        tabs = QTabWidget()
        tabs.addTab(MilestoneView(self.aggregator, self.milestones, self.settings), "마일스톤 기록")
        tabs.addTab(StatsView(self.aggregator, self.settings), "선수/팀 기록")
        tabs.addTab(PredictView(self.aggregator, self.milestones, self.settings), "마일스톤 예측")
        tabs.addTab(RosterView(self.settings), "로스터 편집")
        self.setCentralWidget(tabs)

        status = QStatusBar()
        status.showMessage(
            f"OOTP {self.settings.ootp_version} · 시즌 {self.settings.current_season}"
        )
        self.setStatusBar(status)


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
