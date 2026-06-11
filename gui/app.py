"""QApplication root, setup flow, and main window."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
)

from core.config import AppSettings, SettingsManager, resolve_data_path
from core.db.validation import format_overlap_warning, validate_no_overlap
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from gui.views.initial_import_view import InitialImportView
from gui.views.milestone_view import MilestoneView
from gui.views.predict_view import PredictView
from gui.views.roster_view import RosterView
from gui.views.setup_view import SetupView
from gui.views.stats_view import StatsView


class MainWindow(QMainWindow):
    data_refreshed = pyqtSignal(str)

    def __init__(
        self,
        settings: AppSettings | None = None,
        settings_manager: SettingsManager | None = None,
    ) -> None:
        super().__init__()
        self.settings_manager = settings_manager or SettingsManager()
        self.settings = settings or self.settings_manager.load()

        self.setWindowTitle("OOTP Milestone Tracker")
        self.resize(1100, 720)

        self._aggregator = Aggregator(resolve_data_path(self.settings.db_path))
        self._milestones = load_milestones(
            resolve_data_path(self.settings.milestones_path)
        )

        self._milestone_view: MilestoneView | None = None
        self._stats_view: StatsView | None = None
        self._predict_view: PredictView | None = None
        self._initial_import_view: InitialImportView | None = None

        self._tabs = QTabWidget()
        self.data_refreshed.connect(self._route_data_refreshed)
        self._build_tabs()
        self.setCentralWidget(self._tabs)

        self._status = QStatusBar()
        self._update_status_message()
        self._status.mousePressEvent = self._on_status_clicked  # type: ignore[method-assign]
        self.setStatusBar(self._status)

        self._check_overlap_warning()

    def _build_tabs(self) -> None:
        self._tabs.clear()
        self._milestone_view = MilestoneView(
            self._aggregator, self._milestones, self.settings
        )
        self._tabs.addTab(self._milestone_view, "마일스톤 기록")

        self._stats_view = StatsView(
            self._aggregator,
            self.settings,
            self._milestones,
            self.settings_manager,
        )
        self._stats_view.import_finished.connect(self._on_boxscore_import_finished)
        self._tabs.addTab(self._stats_view, "선수 기록")

        self._predict_view = PredictView(
            self._aggregator, self._milestones, self.settings
        )
        self._tabs.addTab(self._predict_view, "마일스톤 예측")

        self._initial_import_view = InitialImportView(
            self._aggregator, self.settings, self.settings_manager
        )
        self._initial_import_view.import_finished.connect(self._on_init_import_finished)
        self._tabs.addTab(self._initial_import_view, "초기값 설정")

        self._tabs.addTab(RosterView(self.settings), "레이팅 편집")

        setup_tab = SetupView(self.settings_manager, self.settings, embedded=True)
        setup_tab.setup_completed.connect(self._on_setup_tab_saved)
        setup_tab.confirm_button.setText("설정 저장")
        self._tabs.addTab(setup_tab, "설정")

        self._connect_tab_signals()

    def _connect_tab_signals(self) -> None:
        if self._milestone_view:
            try:
                self._milestone_view.records_changed.disconnect()
            except TypeError:
                pass
            self._milestone_view.records_changed.connect(
                lambda: self.data_refreshed.emit("milestone")
            )

    def _route_data_refreshed(self, kind: str) -> None:
        if self._milestone_view and kind in ("boxscore", "milestone", "all"):
            self._milestone_view.on_data_refreshed(kind)
        if self._stats_view and kind in ("boxscore", "init", "all"):
            self._stats_view.on_data_refreshed(kind)
        if self._predict_view and kind in ("boxscore", "init", "milestone", "all"):
            self._predict_view.on_data_refreshed(kind)
        if kind in ("boxscore", "init", "all"):
            self._check_overlap_warning()

    def _on_setup_tab_saved(self, settings: AppSettings) -> None:
        self.settings = settings
        self._update_status_message()
        self._build_tabs()
        self.data_refreshed.emit("all")

    def _on_boxscore_import_finished(self, _message: str) -> None:
        self._update_status_message()
        self.data_refreshed.emit("boxscore")

    def _on_init_import_finished(self) -> None:
        self._update_status_message()
        self.data_refreshed.emit("init")

    def _check_overlap_warning(self) -> None:
        if not self._stats_view:
            return
        overlaps = validate_no_overlap(self._aggregator.conn)
        if overlaps:
            self._stats_view.banner.show_warning(format_overlap_warning(overlaps))

    def _update_status_message(self) -> None:
        league = self.settings.active_save or "(리그 미선택)"
        summary = self._aggregator.get_db_summary()
        last_import = self.settings.import_state.get("last_import_at", "")
        last_label = last_import[:10] if last_import else "-"
        teams = (
            ", ".join(self.settings.tracked_teams)
            if self.settings.tracked_teams
            else "전체"
        )
        self._status.showMessage(
            f"리그: {league} · 시즌 {self.settings.current_season} · "
            f"추적팀: {teams} · 마지막 가져오기: {last_label} · "
            f"DB: {summary['games']}경기 / 선수 {summary['players']}명 "
            f"(클릭하여 설정)"
        )

    def _on_status_clicked(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_setup_dialog()

    def open_setup_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("리그 설정")
        dialog.resize(640, 520)

        setup = SetupView(self.settings_manager, self.settings, dialog)
        setup.setup_completed.connect(
            lambda updated: self._apply_settings(dialog, updated)
        )

        layout = QVBoxLayout(dialog)
        layout.addWidget(setup)
        dialog.exec()

    def _apply_settings(self, dialog: QDialog, settings: AppSettings) -> None:
        self.settings = settings
        self._update_status_message()
        self._build_tabs()
        self.data_refreshed.emit("all")
        dialog.accept()


class _SetupWindow(QMainWindow):
    """Standalone window shown on first run."""

    setup_finished = pyqtSignal(object)

    def __init__(self, settings_manager: SettingsManager) -> None:
        super().__init__()
        self.settings_manager = settings_manager
        self._confirmed = False

        self.setWindowTitle("OOTP Milestone Tracker — 설정")
        self.resize(640, 520)

        setup = SetupView(settings_manager, parent=self)
        setup.setup_completed.connect(self._on_completed)
        self.setCentralWidget(setup)

    def _on_completed(self, settings: AppSettings) -> None:
        self._confirmed = True
        self.setup_finished.emit(settings)
        self.close()

    def closeEvent(self, event) -> None:
        if not self._confirmed:
            QApplication.instance().quit()
        super().closeEvent(event)


def run_app() -> None:
    app = QApplication(sys.argv)
    settings_manager = SettingsManager()

    main_ref: list[MainWindow] = []

    def show_main(settings: AppSettings | None = None) -> MainWindow:
        window = MainWindow(settings=settings, settings_manager=settings_manager)
        window.show()
        main_ref.append(window)
        return window

    if settings_manager.is_setup_complete():
        show_main()
    else:
        setup_window = _SetupWindow(settings_manager)
        setup_window.setup_finished.connect(show_main)
        setup_window.show()

    sys.exit(app.exec())
