"""QApplication root, setup flow, and main window."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, SettingsManager, get_bundle_root, resolve_data_path
from core.i18n import format_full_datetime, format_relative_datetime, tr
from core.db.validation import format_overlap_warning, validate_no_overlap
from core.import_workflow import (
    OUTCOME_COMPLETED,
    OUTCOME_CANCELLED,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL_SUCCESS,
    STEP_ANALYZE_CLASSIFY,
    STEP_REVIEW_RESULTS,
    STEP_SAVE,
    WORKFLOW_BASELINE_HISTORY,
    WORKFLOW_LATEST_BOXSCORES,
    WORKFLOW_NEWS_MESSAGES,
    WORKFLOW_SEASON_FINALIZE,
    advance_import_workflow,
    ensure_import_workflow_schema,
    finish_import_workflow,
    load_all_import_workflow_states,
    load_import_workflow_state,
    start_import_workflow,
)
from core.milestone.definitions import load_milestones
from core.stats.aggregator import Aggregator
from gui.sidebar_nav import SidebarNav
from gui.theme import apply_app_theme
from gui.views.advanced_tools_view import AdvancedToolsView
from gui.views.dashboard_view import DashboardView
from gui.views.import_center_view import ImportCenterView
from gui.views.initial_import_view import InitialImportView
from gui.views.milestone_view import MilestoneView
from gui.views.predict_view import PredictView
from gui.views.roster_view import RosterView
from gui.views.setup_view import SetupView
from gui.views.stats_view import StatsView
from gui.views.streak_view import StreakView
from gui.ui_compact import MAIN_WINDOW_SIZE, SETUP_WINDOW_SIZE, compact_widget


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
        self.settings = self.settings_manager.ensure_derived_paths(self.settings)

        self.setWindowTitle("OOTP Milestone Tracker")
        self.resize(*MAIN_WINDOW_SIZE)

        self._aggregator = Aggregator(resolve_data_path(self.settings.db_path))
        ensure_import_workflow_schema(self._aggregator.conn)
        from core.milestone.message_automation.processed import (
            ensure_processed_messages_schema,
        )

        ensure_processed_messages_schema(self._aggregator.conn)
        self._milestones = load_milestones(
            resolve_data_path(self.settings.milestones_path)
        )

        self._dashboard_view: DashboardView | None = None
        self._milestone_view: MilestoneView | None = None
        self._stats_view: StatsView | None = None
        self._predict_view: PredictView | None = None
        self._streak_view: StreakView | None = None
        self._import_center_view: ImportCenterView | None = None
        self._initial_import_view: InitialImportView | None = None
        self._manual_records_page: QWidget | None = None
        self._rating_editor_view: RosterView | None = None
        self._setup_tab: SetupView | None = None
        self._advanced_tools_view: AdvancedToolsView | None = None
        self._message_review_view: QWidget | None = None
        self._message_fingerprints: dict[str, object] = {}
        self._setup_tab_index: int = SidebarNav.SETUP_PAGE_INDEX

        self._sidebar = SidebarNav()
        self._stack = QStackedWidget()
        self._stack.setObjectName("mainStack")

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._sidebar)

        content_wrap = QWidget()
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._stack, stretch=1)
        shell_layout.addWidget(content_wrap, stretch=1)

        self.data_refreshed.connect(self._route_data_refreshed)
        self._build_pages()
        self.setCentralWidget(shell)

        self._sidebar.page_changed.connect(self._on_main_page_changed)

        self._status = QStatusBar()
        self._update_status_message()
        self._status.mousePressEvent = self._on_status_clicked  # type: ignore[method-assign]
        self.setStatusBar(self._status)

        self._check_overlap_warning()

    def _initial_import_in_progress(self) -> bool:
        return bool(
            self._initial_import_view
            and self._initial_import_view.has_active_operation()
        )

    def _show_initial_import_blocked(self, action: str) -> None:
        QMessageBox.information(
            self,
            tr("Import In Progress"),
            tr(
                "The initial stats import is still running. Wait for it to finish before {action}."
            ).format(action=action),
        )

    def _build_pages(self) -> bool:
        if self._initial_import_in_progress():
            self._show_initial_import_blocked(tr("reloading the application pages"))
            return False
        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            if widget is not None:
                widget.deleteLater()

        self._dashboard_view = DashboardView(
            self._aggregator,
            self._milestones,
            self.settings,
            self.settings_manager,
        )
        self._dashboard_view.import_finished.connect(self._on_boxscore_import_finished)
        self._dashboard_view.navigate_to_milestone.connect(self._navigate_to_milestone)
        self._dashboard_view.navigate_to_predict.connect(self._navigate_to_predict)
        self._dashboard_view.navigate_to_initial_import.connect(
            self._navigate_to_initial_import
        )
        self._dashboard_view.navigate_to_import_center.connect(
            self._navigate_to_import_center
        )
        self._dashboard_view.navigate_to_settings.connect(self._navigate_to_settings)
        self._dashboard_view.navigate_to_review_filter.connect(
            self._navigate_to_review_filter
        )
        self._stack.addWidget(self._dashboard_view)

        self._milestone_view = MilestoneView(
            self._aggregator,
            self._milestones,
            self.settings,
            self.settings_manager,
        )
        self._milestone_view.import_finished.connect(self._on_boxscore_import_finished)
        self._milestone_view.player_detail_requested.connect(
            self._navigate_to_player_details
        )
        self._stack.addWidget(self._milestone_view)

        self._stats_view = StatsView(
            self._aggregator,
            self.settings,
            self._milestones,
            self.settings_manager,
        )
        self._stats_view.import_finished.connect(self._on_boxscore_import_finished)
        self._stack.addWidget(self._stats_view)

        self._predict_view = PredictView(
            self._aggregator, self._milestones, self.settings
        )
        self._predict_view.player_detail_requested.connect(
            self._navigate_to_player_details
        )
        self._stack.addWidget(self._predict_view)

        self._streak_view = StreakView(self._aggregator, self.settings.current_season)
        self._stack.addWidget(self._streak_view)

        self._import_center_view = ImportCenterView()
        self._import_center_view.workflow_action_requested.connect(
            self._on_import_center_action
        )
        self._import_center_view.result_action_requested.connect(
            self._on_import_center_result_action
        )
        self._refresh_import_workflow_views()
        self._stack.addWidget(self._import_center_view)

        self._initial_import_view = InitialImportView(
            self._aggregator, self.settings, self.settings_manager
        )
        self._initial_import_view.import_finished.connect(self._on_init_import_finished)
        self._manual_records_page = self._build_manual_records_page()
        self._stack.addWidget(self._manual_records_page)

        self._rating_editor_view = RosterView(self.settings)
        self._stack.addWidget(self._rating_editor_view)

        setup_tab = SetupView(self.settings_manager, self.settings, embedded=True)
        setup_tab.setup_completed.connect(self._on_setup_tab_saved)
        setup_tab.milestones_changed.connect(self._reload_milestones)
        setup_tab.bundle_updates_changed.connect(self._refresh_settings_tab_badge)
        setup_tab.save_database_reset_prepare.connect(self._prepare_save_database_reset)
        setup_tab.save_database_reset.connect(self._on_save_database_reset)
        setup_tab.boxscore_reimported.connect(self._on_boxscore_reimported)
        setup_tab.confirm_button.setText(tr("Settings saved"))
        setup_tab.confirm_button.setObjectName("primaryButton")
        self._setup_tab = setup_tab
        self._stack.addWidget(setup_tab)

        self._advanced_tools_view = AdvancedToolsView(
            self.settings_manager, self.settings
        )
        self._advanced_tools_view.save_database_reset_prepare.connect(
            self._prepare_save_database_reset
        )
        self._advanced_tools_view.save_database_reset.connect(self._on_save_database_reset)
        self._advanced_tools_view.boxscore_reimported.connect(self._on_boxscore_reimported)
        self._stack.addWidget(self._advanced_tools_view)

        self._stack.addWidget(self._initial_import_view)
        self._initial_import_view.hide()

        self._connect_tab_signals()
        for index in range(self._stack.count()):
            widget = self._stack.widget(index)
            if widget is not None:
                compact_widget(widget)

        previous = self._sidebar.current_index()
        self._sidebar.set_current_index(min(previous, self._stack.count() - 1), emit=False)
        self._stack.setCurrentIndex(self._sidebar.current_index())
        self._refresh_settings_tab_badge()
        return True

    def _set_current_page(self, widget: QWidget) -> None:
        index = self._stack.indexOf(widget)
        if index < 0:
            return
        self._sidebar.set_current_index(index)
        self._stack.setCurrentIndex(index)

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
        if self._dashboard_view and kind in (
            "boxscore",
            "init",
            "milestone",
            "all",
            "settings",
        ):
            self._dashboard_view.on_data_refreshed(kind)
        if self._milestone_view and kind in ("boxscore", "milestone", "all"):
            self._milestone_view.on_data_refreshed(kind)
        if self._stats_view and kind in ("boxscore", "init", "all"):
            self._stats_view.on_data_refreshed(kind)
        if self._predict_view and kind in ("boxscore", "init", "milestone", "all"):
            self._predict_view.on_data_refreshed(kind)
        if self._streak_view and kind in ("boxscore", "milestone", "all"):
            self._streak_view._load()
        if self._advanced_tools_view and kind in ("boxscore", "init", "milestone", "all"):
            self._advanced_tools_view.refresh_database_summary()
        if kind in ("boxscore", "init", "all"):
            self._check_overlap_warning()
        self._refresh_import_workflow_views()

    def _navigate_to_milestone(self, record: dict) -> None:
        if self._milestone_view:
            record_id = record.get("id") if record else None
            if record_id:
                self._milestone_view.highlight_record(int(record_id))
            elif record and record.get("scope"):
                self._milestone_view.focus_scope(str(record["scope"]))
            self._set_current_page(self._milestone_view)

    def _navigate_to_predict(self, player_id: int, milestone_key: str) -> None:
        if self._predict_view:
            self._set_current_page(self._predict_view)
            pid = player_id if player_id >= 0 else None
            self._predict_view.focus_player(pid, near_only=bool(milestone_key))

    def _navigate_to_player_details(self, player_id: int) -> None:
        if self._stats_view:
            self._set_current_page(self._stats_view)
            self._stats_view.focus_player(player_id)

    def _navigate_to_initial_import(self) -> None:
        if self._initial_import_view:
            self._set_current_page(self._initial_import_view)

    def _navigate_to_import_center(self) -> None:
        if self._import_center_view:
            self._set_current_page(self._import_center_view)

    def _navigate_to_settings(self) -> None:
        if self._setup_tab:
            self._set_current_page(self._setup_tab)

    def _navigate_to_review_filter(self, filter_key: str) -> None:
        if filter_key in ("news_messages", "date_missing", "message_errors"):
            if self._message_review_view is None:
                self._open_message_review_from_save()
            if self._message_review_view is not None:
                combo = getattr(self._message_review_view, "filter_combo", None)
                target = {
                    "date_missing": "date_needed",
                    "message_errors": "error",
                }.get(filter_key, "all")
                if combo is not None:
                    index = combo.findData(target)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                self._set_current_page(self._message_review_view)
            return
        if self._milestone_view:
            self._set_current_page(self._milestone_view)

    def _build_manual_records_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        title = QLabel(tr("Manual Records"))
        title.setObjectName("pageTitle")
        description = QLabel(
            tr("Add milestone, award, team move, or injury records with guided forms.")
        )
        description.setWordWrap(True)
        description.setObjectName("mutedLabel")
        open_button = QPushButton(tr("Open manual record entry"))
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self._open_manual_records_dialog)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(open_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _open_manual_records_dialog(self) -> None:
        from gui.widgets.manual_milestone_dialog import ManualMilestoneDialog

        dialog = ManualMilestoneDialog(
            self._aggregator,
            self._milestones,
            self.settings,
            parent=self,
        )
        if dialog.exec():
            self.data_refreshed.emit("milestone")

    def _on_import_center_action(self, workflow_id: str, action_id: str) -> None:
        workflow_id = (
            WORKFLOW_LATEST_BOXSCORES
            if workflow_id == "latest_games"
            else workflow_id
        )
        if action_id.startswith("open:"):
            self._route_workflow_open(workflow_id, action_id)
            return
        if action_id == "source_check":
            self._check_workflow_source(workflow_id)
            return
        if workflow_id == WORKFLOW_LATEST_BOXSCORES:
            if action_id == STEP_ANALYZE_CLASSIFY and self._milestone_view:
                advance_import_workflow(
                    self._aggregator.conn,
                    workflow_id,
                    current_step=STEP_SAVE,
                    message=tr("Importing new and changed boxscores."),
                )
                self._refresh_import_workflow_views()
                self._set_current_page(self._milestone_view)
                self._milestone_view.start_import()
            elif self._milestone_view:
                self._set_current_page(self._milestone_view)
            return
        if workflow_id == WORKFLOW_BASELINE_HISTORY:
            if action_id == STEP_ANALYZE_CLASSIFY:
                advance_import_workflow(
                    self._aggregator.conn,
                    workflow_id,
                    current_step=STEP_REVIEW_RESULTS,
                    message=tr("Review the comparison before importing baseline records."),
                )
                self._refresh_import_workflow_views()
            if self._initial_import_view:
                self._set_current_page(self._initial_import_view)
            return
        if workflow_id == WORKFLOW_SEASON_FINALIZE:
            if action_id == STEP_ANALYZE_CLASSIFY:
                self._analyze_season_finalize_workflow()
            elif action_id == STEP_SAVE:
                self._run_season_finalize_workflow()
                return
            if self._milestone_view:
                self._set_current_page(self._milestone_view)
            return
        if workflow_id == WORKFLOW_NEWS_MESSAGES:
            if action_id in (STEP_ANALYZE_CLASSIFY, STEP_REVIEW_RESULTS):
                self._open_message_review_from_save()
            elif action_id == STEP_SAVE and self._message_review_view is not None:
                save = getattr(self._message_review_view, "save_approved", None)
                if callable(save):
                    save()

    def _on_import_center_result_action(self, workflow_id: str, action: str) -> None:
        if action == "view_records":
            if workflow_id == WORKFLOW_BASELINE_HISTORY and self._initial_import_view:
                self._set_current_page(self._initial_import_view)
                return
            source_by_workflow = {
                WORKFLOW_LATEST_BOXSCORES: "boxscore_auto",
                WORKFLOW_NEWS_MESSAGES: "message_auto",
                WORKFLOW_SEASON_FINALIZE: "season_final",
            }
            self._show_milestone_source(source_by_workflow.get(workflow_id, ""))
        elif action in ("view_differences",) and self._initial_import_view:
            self._set_current_page(self._initial_import_view)
        elif action == "review_issues" and workflow_id == WORKFLOW_NEWS_MESSAGES and self._message_review_view is not None:
            combo = getattr(self._message_review_view, "filter_combo", None)
            if combo is not None:
                index = combo.findData("all")
                if index >= 0:
                    combo.setCurrentIndex(index)
            self._set_current_page(self._message_review_view)
        elif action == "review_issues" and workflow_id == WORKFLOW_SEASON_FINALIZE:
            self._show_milestone_source("season_final")
        elif action == "review_issues" and workflow_id == WORKFLOW_BASELINE_HISTORY and self._initial_import_view:
            self._set_current_page(self._initial_import_view)
        elif action in ("view_errors", "check_errors") and workflow_id == WORKFLOW_NEWS_MESSAGES and self._message_review_view is not None:
            combo = getattr(self._message_review_view, "filter_combo", None)
            if combo is not None:
                index = combo.findData("error")
                if index >= 0:
                    combo.setCurrentIndex(index)
            self._set_current_page(self._message_review_view)
        elif action in ("view_errors", "check_errors"):
            if workflow_id == WORKFLOW_BASELINE_HISTORY and self._initial_import_view:
                self._set_current_page(self._initial_import_view)
            self._show_persisted_workflow_error(workflow_id)
        elif self._import_center_view:
            self._set_current_page(self._import_center_view)

    def _show_milestone_source(self, source: str) -> None:
        if self._milestone_view is None:
            return
        combo = getattr(self._milestone_view, "source_combo", None)
        if combo is not None and source:
            index = combo.findData(source)
            if index >= 0:
                combo.setCurrentIndex(index)
        self._set_current_page(self._milestone_view)

    def _show_persisted_workflow_error(self, workflow_id: str) -> None:
        """Show the persisted report, so result actions survive app restart."""

        state = load_import_workflow_state(self._aggregator.conn, workflow_id)
        detail = state.message or tr("No error detail was recorded for this run.")
        if state.report_ref:
            detail = f"{detail}\n\n{tr('Report')}: {state.report_ref}"
        QMessageBox.warning(self, tr("Import errors"), detail)

    def _refresh_import_workflow_views(self) -> None:
        if self._aggregator.is_closed:
            return
        states = load_all_import_workflow_states(self._aggregator.conn)
        if self._import_center_view is not None:
            for workflow_id, state in states.items():
                self._import_center_view.apply_workflow_state(workflow_id, state)

    def _check_workflow_source(self, workflow_id: str) -> None:
        start_import_workflow(
            self._aggregator.conn,
            workflow_id,
            message=tr("Checking source files."),
        )
        if workflow_id == WORKFLOW_LATEST_BOXSCORES:
            folder = Path(self.settings.boxscore_dir)
            files = (
                list(folder.glob("*.html")) + list(folder.glob("*.txt"))
                if folder.is_dir()
                else []
            )
            if not files:
                self._fail_workflow_source(workflow_id, tr("No boxscore source files were found."))
                return
            totals = {"processed": len(files)}
        elif workflow_id == WORKFLOW_NEWS_MESSAGES:
            files = self._message_files()
            if not files:
                self._fail_workflow_source(workflow_id, tr("No news message files were found."))
                return
            totals = {"processed": len(files)}
        elif workflow_id == WORKFLOW_BASELINE_HISTORY:
            folder = Path(self.settings.initial_stats_dir)
            required = (
                folder / "player_batting_stats.txt",
                folder / "player_pitching_stats.txt",
            )
            present = sum(path.is_file() for path in required)
            if present < len(required):
                self._fail_workflow_source(
                    workflow_id,
                    tr("Required batting and pitching baseline files were not found."),
                )
                return
            totals = {"processed": present}
        elif workflow_id == WORKFLOW_SEASON_FINALIZE:
            season = int(self.settings.current_season or 0)
            if season <= 0 or self._milestone_view is None:
                self._fail_workflow_source(
                    workflow_id, tr("Select a valid current season first.")
                )
                return
            batting_path, pitching_path = self._milestone_view._season_export_paths()
            missing = [
                str(path)
                for path in (batting_path, pitching_path)
                if not Path(path).is_file()
            ]
            if missing:
                self._fail_workflow_source(
                    workflow_id,
                    tr("Required season batting and pitching exports were not found."),
                )
                return
            totals = {"processed": 2, "season": season}
        else:
            totals = {}
        advance_import_workflow(
            self._aggregator.conn,
            workflow_id,
            current_step=STEP_ANALYZE_CLASSIFY,
            totals=totals,
            message=tr("Source files are ready for analysis."),
        )
        self._refresh_import_workflow_views()
        self.data_refreshed.emit("all")

    def _analyze_season_finalize_workflow(self) -> None:
        """Build a real, non-writing preview before enabling final save."""

        if self._milestone_view is None:
            return
        from core.milestone.checker import MilestoneChecker
        from core.stats.initial_import import InitialImporter

        season = int(self.settings.current_season or 0)
        batting_path, pitching_path = self._milestone_view._season_export_paths()
        try:
            importer = InitialImporter(self._aggregator)
            snapshot = importer.read_season_snapshot(
                batting_path,
                pitching_path,
                season=season,
            )
            validation = importer.validate_season_snapshot(snapshot)
            if validation.status != "complete":
                raise ValueError(
                    tr("Season exports are incomplete or do not contain the current season.")
                )
            checker = MilestoneChecker(
                self._aggregator,
                self._milestones,
                season_games_total=self.settings.season_games_total,
                ratio_qualifiers=self.settings.get_ratio_qualifiers(),
                tracked_teams=self.settings.tracked_teams,
                custom_teams=self.settings.custom_mlb_teams,
            )
            candidates = checker.check_season_ratios(
                season,
                achieved_date=f"{season}-12-31",
                totals_override=snapshot.as_totals_override(),
            )
        except Exception as exc:
            self._fail_workflow_source(WORKFLOW_SEASON_FINALIZE, str(exc))
            return
        totals = {
            "season": season,
            "processed": len(candidates),
            "candidates": len(candidates),
        }
        advance_import_workflow(
            self._aggregator.conn,
            WORKFLOW_SEASON_FINALIZE,
            current_step=STEP_REVIEW_RESULTS,
            totals=totals,
            unresolved={},
            message=tr(
                "{count} season-final candidate(s) are ready for confirmation."
            ).format(count=len(candidates)),
        )
        self._refresh_import_workflow_views()

    def _fail_workflow_source(self, workflow_id: str, message: str) -> None:
        finish_import_workflow(
            self._aggregator.conn,
            workflow_id,
            outcome=OUTCOME_FAILED,
            unresolved={"errors": 1},
            message=message,
        )
        if self._import_center_view is not None:
            self._import_center_view.set_error_summary(message, workflow_id=workflow_id)
        self._refresh_import_workflow_views()

    def _route_workflow_open(self, workflow_id: str, action_id: str) -> None:
        route = action_id.rsplit(":", 1)[-1]
        if route in ("records", "saved") and self._milestone_view:
            self._set_current_page(self._milestone_view)
        elif route in ("errors", "review", "candidates") and self._message_review_view is not None:
            combo = getattr(self._message_review_view, "filter_combo", None)
            if combo is not None:
                key = "error" if route == "errors" else "all"
                index = combo.findData(key)
                if index >= 0:
                    combo.setCurrentIndex(index)
            self._set_current_page(self._message_review_view)
        elif workflow_id == WORKFLOW_BASELINE_HISTORY and self._initial_import_view:
            self._set_current_page(self._initial_import_view)
        elif workflow_id == WORKFLOW_LATEST_BOXSCORES and self._milestone_view:
            self._set_current_page(self._milestone_view)
        elif workflow_id == WORKFLOW_NEWS_MESSAGES:
            self._open_message_review_from_save()
        elif workflow_id == WORKFLOW_SEASON_FINALIZE and self._milestone_view:
            self._set_current_page(self._milestone_view)

    def _run_season_finalize_workflow(self) -> None:
        if self._milestone_view is None:
            return
        advance_import_workflow(
            self._aggregator.conn,
            WORKFLOW_SEASON_FINALIZE,
            current_step=STEP_SAVE,
            message=tr("Recording season finalization results."),
        )
        try:
            result = self._milestone_view._record_season_ratio_milestones()
        except Exception as exc:
            finish_import_workflow(
                self._aggregator.conn,
                WORKFLOW_SEASON_FINALIZE,
                outcome=OUTCOME_FAILED,
                totals={"processed": 1, "errors": 1},
                unresolved={"errors": 1},
                message=str(exc),
            )
            if self._import_center_view:
                self._import_center_view.set_error_summary(
                    str(exc),
                    {"processed": 1, "errors": 1},
                    workflow_id=WORKFLOW_SEASON_FINALIZE,
                )
            self._refresh_import_workflow_views()
            return
        totals = dict(result.as_workflow_totals())
        totals["season"] = int(result.season)
        outcome = str(result.outcome)
        finish_import_workflow(
            self._aggregator.conn,
            WORKFLOW_SEASON_FINALIZE,
            outcome=outcome,
            totals=totals,
            unresolved=dict(result.unresolved),
            message=str(result.message),
        )
        if self._import_center_view:
            if outcome == OUTCOME_COMPLETED:
                self._import_center_view.set_completed_summary(
                    totals,
                    {},
                    workflow_id=WORKFLOW_SEASON_FINALIZE,
                )
            elif outcome == OUTCOME_PARTIAL_SUCCESS:
                self._import_center_view.set_partial_success_summary(
                    totals,
                    dict(result.unresolved),
                    workflow_id=WORKFLOW_SEASON_FINALIZE,
                )
            elif outcome == OUTCOME_FAILED:
                self._import_center_view.set_error_summary(
                    str(result.message),
                    totals,
                    workflow_id=WORKFLOW_SEASON_FINALIZE,
                )
            else:
                self._import_center_view.set_cancelled_summary(
                    totals,
                    workflow_id=WORKFLOW_SEASON_FINALIZE,
                )
        self._refresh_import_workflow_views()
        self.data_refreshed.emit("milestone")

    def _message_files(self) -> list[Path]:
        if not self.settings.active_save_path:
            return []
        save_root = Path(self.settings.active_save_path)
        candidates = [
            save_root / "news" / "html" / "messages",
            save_root / "messages",
            save_root / "news" / "messages",
        ]
        files: list[Path] = []
        for directory in candidates:
            if directory.is_dir():
                files.extend(sorted(directory.glob("message*.txt")))
        return files

    def _open_message_review_from_save(self) -> None:
        from core.milestone.message_automation.parser import parse_message
        from core.milestone.message_automation.processed import (
            fingerprint_message_file,
            get_message_rescan_status,
            get_processed_message,
        )
        from gui.views.message_review_view import MessageReviewView
        from gui.widgets.message_review_model import (
            STATUS_APPLIED,
            STATUS_EXCLUDED,
            MessageReviewItem,
        )

        items: list[MessageReviewItem] = []
        self._message_fingerprints = {}
        for path in self._message_files():
            raw = ""
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                fingerprint = fingerprint_message_file(path)
                self._message_fingerprints[path.stem] = fingerprint
                rescan_status = get_message_rescan_status(
                    self._aggregator.conn, fingerprint
                )
                processed = get_processed_message(self._aggregator.conn, path.stem)
                parsed = parse_message(
                    raw,
                    tracked_teams=self.settings.tracked_teams,
                    season_hint=self.settings.current_season,
                    source_id=path.stem,
                )
                item = MessageReviewItem(parsed, raw_text=raw)
                if rescan_status == "already_applied" and processed is not None:
                    item.status = STATUS_APPLIED
                    item.created_record_ids = list(processed.created_record_ids)
                    item.duplicate_record_ids = list(processed.duplicate_record_ids)
                elif rescan_status == "changed_review_needed":
                    item.notice = "changed_source"
                elif rescan_status == "excluded":
                    item.status = STATUS_EXCLUDED
                items.append(item)
            except Exception:
                from core.milestone.message_automation.parser import ParsedMessage

                parsed = ParsedMessage(
                    category="error",
                    title=path.stem,
                    excluded=True,
                    exclusion_reason="file_read_failed",
                    forms=[],
                    source_id=path.stem,
                    player_names={},
                )
                items.append(
                    MessageReviewItem(
                        parsed,
                        raw_text=raw,
                        error="file_read_failed",
                    )
                )

        state = start_import_workflow(
            self._aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            message=tr("Analyzing and classifying news messages."),
        )
        counts = {
            "processed": len(items),
            "created": 0,
            "duplicates": sum(1 for item in items if item.status == STATUS_APPLIED),
            "excluded": sum(1 for item in items if item.status == STATUS_EXCLUDED),
            "date_missing": sum(1 for item in items if item.status == "date_needed"),
            "errors": sum(1 for item in items if item.status == "error"),
        }
        unresolved = {
            "date_missing": counts["date_missing"],
            "errors": counts["errors"],
            "review_needed": sum(
                1 for item in items if item.status in ("candidate", "date_needed")
            ),
        }
        advance_import_workflow(
            self._aggregator.conn,
            state.workflow_id,
            current_step=STEP_REVIEW_RESULTS,
            totals=counts,
            unresolved=unresolved,
            message=tr("Review candidates and approve only records that should be saved."),
        )
        view = MessageReviewView(
            items,
            save_callback=self._save_approved_messages,
            reanalyze_callback=self._reanalyze_message_item,
            parent=self,
        )
        view.save_completed.connect(self._on_message_review_saved)
        view.exclusions_requested.connect(self._persist_message_review_exclusions)
        self._stack.addWidget(view)
        self._message_review_view = view
        self._set_current_page(view)
        if self._import_center_view:
            self._import_center_view.set_partial_success_summary(
                {"messages": len(items), "record_candidates": sum(item.generated_count for item in items)},
                {
                    "date_needed": sum(1 for item in items if item.status == "date_needed"),
                    "excluded": sum(1 for item in items if item.status == "excluded"),
                    "errors": sum(1 for item in items if item.status == "error"),
                },
                workflow_id=WORKFLOW_NEWS_MESSAGES,
            )
        self._refresh_import_workflow_views()

    def _persist_message_review_exclusions(self, items: object) -> None:
        """Persist explicit reviewer exclusions immediately and durably."""

        from core.milestone.message_automation.processed import (
            upsert_processed_message,
        )

        for item in list(items or []) if isinstance(items, list) else []:
            source_id = str(getattr(item, "source_id", ""))
            fingerprint = self._message_fingerprints.get(source_id)
            if fingerprint is None:
                continue
            parsed = getattr(item, "parsed", None)
            upsert_processed_message(
                self._aggregator.conn,
                fingerprint=fingerprint,
                status="excluded",
                category=str(getattr(parsed, "category", "") or ""),
                exclusion_reason="excluded_by_reviewer",
            )
        self._refresh_import_workflow_views()

    def _reanalyze_message_item(self, item: object) -> object:
        from core.milestone.message_automation.parser import parse_message

        return parse_message(
            str(getattr(item, "raw_text", "")),
            tracked_teams=self.settings.tracked_teams,
            message_date=getattr(item, "message_date", None),
            season_hint=self.settings.current_season,
            source_id=str(getattr(item, "source_id", "")),
        )

    def _save_approved_messages(self, parsed_messages: list[object]) -> list[object]:
        from core.milestone.checker import MilestoneChecker
        from core.milestone.message_automation.recorder import (
            record_parsed_message_result,
        )

        checker = MilestoneChecker(
            self._aggregator,
            self._milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        advance_import_workflow(
            self._aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            current_step=STEP_SAVE,
            message=tr("Saving approved message records."),
        )
        results: list[object] = []
        for parsed in parsed_messages:
            fingerprint = self._message_fingerprints.get(
                str(getattr(parsed, "source_id", ""))
            )
            results.append(
                record_parsed_message_result(
                    checker,
                    parsed,
                    fingerprint=fingerprint,
                )
            )
        self.data_refreshed.emit("milestone")
        return results

    def _on_message_review_saved(self, result: object) -> None:
        rows = list(result or []) if isinstance(result, list) else []
        created = sum(
            len(getattr(row, "created_record_ids", []) or []) for row in rows
        )
        duplicates = sum(
            len(getattr(row, "duplicate_record_ids", []) or []) for row in rows
        )
        errors = sum(len(getattr(row, "errors", []) or []) for row in rows)
        review_counts: dict[str, int] = {}
        if self._message_review_view is not None:
            model = getattr(self._message_review_view, "model", None)
            if model is not None and hasattr(model, "summary_counts"):
                review_counts = dict(model.summary_counts())
        review_needed = int(review_counts.get("candidates", 0) or 0)
        date_missing = int(review_counts.get("date_needed", 0) or 0)
        model_errors = int(review_counts.get("errors", 0) or 0)
        excluded = int(review_counts.get("excluded", 0) or 0)
        processed = int(review_counts.get("total", 0) or 0)
        unresolved = {
            "review_needed": review_needed,
            "date_missing": date_missing,
            "errors": max(errors, model_errors),
        }
        has_unresolved = any(unresolved.values())
        saved_any = bool(created or duplicates or int(review_counts.get("applied", 0) or 0))
        outcome = (
            OUTCOME_FAILED
            if unresolved["errors"] and not saved_any
            else OUTCOME_PARTIAL_SUCCESS
            if has_unresolved
            else OUTCOME_COMPLETED
        )
        finish_import_workflow(
            self._aggregator.conn,
            WORKFLOW_NEWS_MESSAGES,
            outcome=outcome,
            totals={
                "processed": processed,
                "created": created,
                "duplicates": duplicates,
                "excluded": excluded,
                "errors": max(errors, model_errors),
            },
            unresolved=unresolved,
            message=tr("Message review save finished."),
        )
        if self._import_center_view:
            totals = {"saved_records": created, "duplicates": duplicates}
            if outcome == OUTCOME_COMPLETED:
                self._import_center_view.set_completed_summary(
                    totals, {}, workflow_id=WORKFLOW_NEWS_MESSAGES
                )
            else:
                self._import_center_view.set_partial_success_summary(
                    totals, unresolved, workflow_id=WORKFLOW_NEWS_MESSAGES
                )
        self._refresh_import_workflow_views()

    def _reload_aggregator(self) -> None:
        target = resolve_data_path(self.settings.db_path)
        if self._aggregator.db_path.resolve() != target.resolve():
            self._aggregator.switch_database(target)
        else:
            self._aggregator.reopen()

    def _prepare_save_database_reset(self) -> None:
        self._aggregator.close()

    def _reopen_aggregator_if_needed(self) -> bool:
        target = resolve_data_path(self.settings.db_path)
        if (
            self._aggregator.db_path.resolve() == target.resolve()
            and not self._aggregator.is_closed
        ):
            return False
        if self._aggregator.db_path.resolve() != target.resolve():
            self._aggregator.switch_database(target)
        else:
            self._aggregator.reopen()
        return True

    def _on_save_database_reset(self) -> None:
        self.settings = self.settings_manager.load()
        self._reload_aggregator()
        self._sync_view_settings()
        self._update_status_message()
        self.data_refreshed.emit("all")

    def _on_boxscore_reimported(self, _message: str) -> None:
        self._reopen_aggregator_if_needed()
        self._sync_view_settings()
        self.data_refreshed.emit("all")
        self._update_status_message()

    def _sync_view_settings(self) -> None:
        from core.stats.initial_import import InitialImporter

        for view in (
            self._dashboard_view,
            self._milestone_view,
            self._stats_view,
            self._predict_view,
            self._initial_import_view,
            self._streak_view,
            self._advanced_tools_view,
        ):
            if view is None:
                continue
            if hasattr(view, "settings"):
                view.settings = self.settings
            if hasattr(view, "set_settings"):
                view.set_settings(self.settings)
            if hasattr(view, "importer"):
                view.importer = InitialImporter(self._aggregator)

    def _apply_settings_changes(self, settings: AppSettings) -> bool:
        if self._initial_import_in_progress():
            self._show_initial_import_blocked(tr("applying settings"))
            return False
        settings = self.settings_manager.ensure_derived_paths(settings)
        self.settings = settings
        self._reload_aggregator()
        self._sync_view_settings()
        self._update_status_message()
        self._build_pages()
        self.data_refreshed.emit("all")
        return True

    def _on_setup_tab_saved(self, settings: AppSettings) -> None:
        self._apply_settings_changes(settings)

    def _reload_milestones(self) -> None:
        self._milestones = load_milestones(
            resolve_data_path(self.settings.milestones_path)
        )
        for view in (
            self._dashboard_view,
            self._milestone_view,
            self._stats_view,
            self._predict_view,
            self._streak_view,
        ):
            if view is not None:
                view.milestones = self._milestones
        self.data_refreshed.emit("all")
        self._refresh_settings_tab_badge()

    def _on_main_page_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if self._setup_tab is not None and index == self._setup_tab_index:
            self._setup_tab.refresh_bundle_updates_status()
        if (
            self._advanced_tools_view is not None
            and index == SidebarNav.ADVANCED_TOOLS_PAGE_INDEX
        ):
            self._advanced_tools_view.refresh_database_summary()

    def _refresh_settings_tab_badge(self) -> None:
        from core.config.bundle_updates import pending_update_count

        pending = pending_update_count()
        if pending > 0:
            self._sidebar.set_setup_badge_visible(
                True,
                tr("Bundle update available") + f" ({pending})",
            )
        else:
            self._sidebar.set_setup_badge_visible(False)

    def _on_boxscore_import_finished(self, payload: object) -> None:
        """Persist the worker's structured terminal outcome without text parsing."""

        required = ("outcome", "processed", "created", "duplicates", "errors")
        if not all(hasattr(payload, name) for name in required):
            raise TypeError("Boxscore import completion requires ImportFinishedPayload.")
        self._update_status_message()
        outcome = str(getattr(payload, "outcome"))
        message = str(getattr(payload, "message", ""))
        totals = {
            "processed": int(getattr(payload, "processed", 0) or 0),
            "created": int(getattr(payload, "created", 0) or 0),
            "duplicates": int(getattr(payload, "duplicates", 0) or 0),
            "excluded": int(getattr(payload, "excluded", 0) or 0),
            "errors": int(getattr(payload, "errors", 0) or 0),
        }
        unresolved = dict(getattr(payload, "unresolved", {}) or {})
        report_ref = self._persist_boxscore_error_report(payload)
        aggregator = getattr(self, "_aggregator", None)
        if aggregator is not None and not aggregator.is_closed:
            finish_import_workflow(
                aggregator.conn,
                WORKFLOW_LATEST_BOXSCORES,
                outcome=outcome,
                totals=totals,
                unresolved=unresolved,
                message=message,
                report_ref=report_ref,
            )
        if self._import_center_view is not None:
            if outcome == OUTCOME_COMPLETED:
                self._import_center_view.set_completed_summary(
                    totals, {}, workflow_id=WORKFLOW_LATEST_BOXSCORES
                )
            elif outcome == OUTCOME_PARTIAL_SUCCESS:
                self._import_center_view.set_partial_success_summary(
                    totals, unresolved, workflow_id=WORKFLOW_LATEST_BOXSCORES
                )
            elif outcome == OUTCOME_CANCELLED:
                self._import_center_view.set_cancelled_summary(
                    totals, workflow_id=WORKFLOW_LATEST_BOXSCORES
                )
            else:
                self._import_center_view.set_error_summary(
                    message, totals, workflow_id=WORKFLOW_LATEST_BOXSCORES
                )
        self.data_refreshed.emit("boxscore")

    def _persist_boxscore_error_report(self, payload: object) -> str:
        batch = getattr(payload, "batch", None)
        errors = list(getattr(batch, "errors", []) or [])
        if not errors:
            return ""
        report_dir = Path(self._aggregator.db_path).parent / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "latest_boxscores_last_errors.json"
        rows = [
            {
                "game_id": int(getattr(error, "game_id", 0) or 0),
                "file": str(
                    getattr(error, "file_path", "")
                    or getattr(error, "filename", "")
                    or ""
                ),
                "error": str(getattr(error, "error", error)),
            }
            for error in errors
        ]
        report_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(report_path)

    def _on_init_import_finished(self) -> None:
        self._update_status_message()
        aggregator = getattr(self, "_aggregator", None)
        if aggregator is not None and not aggregator.is_closed:
            finish_import_workflow(
                aggregator.conn,
                WORKFLOW_BASELINE_HISTORY,
                outcome=OUTCOME_COMPLETED,
                message=tr("Career and historical records were imported."),
            )
        if self._import_center_view is not None:
            self._import_center_view.set_completed_summary(
                {
                    tr("workflow"): tr("career and historical records"),
                    tr("status"): tr("completed"),
                },
                {tr("next action"): tr("review records or import latest games")},
                workflow_id=WORKFLOW_BASELINE_HISTORY,
            )
        self.data_refreshed.emit("init")

    def _check_overlap_warning(self) -> None:
        if not self._stats_view:
            return
        overlaps = validate_no_overlap(self._aggregator.conn)
        if overlaps:
            self._stats_view.banner.show_warning(format_overlap_warning(overlaps))

    def _update_status_message(self) -> None:
        league = self.settings.active_save or tr("(No league selected)")
        summary = self._aggregator.get_db_summary()
        last_import = self.settings.import_state.get("last_import_at", "")
        last_label = format_relative_datetime(last_import)
        teams = (
            ", ".join(self.settings.tracked_teams)
            if self.settings.tracked_teams
            else tr("All")
        )
        self._status.showMessage(
            tr(
                "League: {league} · Season {season} · Tracked: {teams} · Last import: {last} · DB: {games} games / {players} players (click to configure)"
            ).format(
                league=league,
                season=self.settings.current_season,
                teams=teams,
                last=last_label,
                games=summary["games"],
                players=summary["players"],
            )
        )
        self._status.setToolTip(format_full_datetime(last_import))
        self._update_sidebar_status()

    def _update_sidebar_status(self) -> None:
        target = resolve_data_path(self.settings.db_path)
        if not self.settings.active_save:
            self._sidebar.set_status(
                level="error",
                status_text=tr("⚠ No league selected"),
                context_text=tr("Select a league in Settings."),
                tooltip=str(target),
            )
        elif self._aggregator.is_closed:
            self._sidebar.set_status(
                level="error",
                status_text=tr("⚠ Data connection issue"),
                context_text=self.settings.active_save,
                tooltip=str(target),
            )
        else:
            self._sidebar.set_status(
                level="ok",
                status_text=tr("● Data OK"),
                context_text=tr("{league} · Season {season}").format(
                    league=self.settings.active_save,
                    season=self.settings.current_season,
                ),
                tooltip=tr("DB: {path}").format(path=target),
            )

    def _on_status_clicked(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_setup_dialog()

    def open_setup_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("League Settings"))
        dialog.resize(*SETUP_WINDOW_SIZE)

        setup = SetupView(self.settings_manager, self.settings, dialog, embedded=True)
        setup.setup_completed.connect(
            lambda updated: self._apply_settings(dialog, updated)
        )
        setup.milestones_changed.connect(self._reload_milestones)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(setup)
        dialog.exec()

    def _apply_settings(self, dialog: QDialog, settings: AppSettings) -> None:
        if self._apply_settings_changes(settings):
            dialog.accept()

    def closeEvent(self, event) -> None:
        if self._initial_import_in_progress():
            self._show_initial_import_blocked(tr("closing the application"))
            event.ignore()
            return
        # Box score import workers (StatsView/MilestoneView) are QThreads
        # parented to their view, not to this window, so they must be
        # stopped explicitly here too -- otherwise Qt destroys a still-
        # running QThread when the app quits.
        if self._stats_view is not None:
            self._stats_view.stop_import_worker()
        if self._milestone_view is not None:
            self._milestone_view.stop_import_worker()
        super().closeEvent(event)


class _LanguageSelectDialog(QDialog):
    """Language picker shown before first-run setup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OOTP Milestone Tracker")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setFixedWidth(380)

        title = QLabel("OOTP Milestone Tracker")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("언어를 선택하세요  /  Select a language")
        subtitle.setObjectName("mutedLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._ko_radio = QRadioButton("한국어 (Korean)")
        self._ko_radio.setChecked(True)
        self._en_radio = QRadioButton("English")

        btn_ok = QPushButton("계속  /  Continue")
        btn_ok.setObjectName("primaryButton")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)

        radio_col = QVBoxLayout()
        radio_col.setSpacing(10)
        radio_col.addWidget(self._ko_radio)
        radio_col.addWidget(self._en_radio)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addLayout(radio_col)
        layout.addSpacing(8)
        layout.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def selected_language(self) -> str:
        return "en" if self._en_radio.isChecked() else "ko"


class _SetupWindow(QMainWindow):
    """Standalone window shown on first run."""

    setup_finished = pyqtSignal(object)

    def __init__(self, settings_manager: SettingsManager) -> None:
        super().__init__()
        self.settings_manager = settings_manager
        self._confirmed = False

        self.setWindowTitle(tr("OOTP Milestone Tracker — Settings"))
        self.resize(*SETUP_WINDOW_SIZE)

        setup = SetupView(settings_manager, parent=self)
        setup.setup_completed.connect(self._on_completed)
        setup.confirm_button.setObjectName("primaryButton")
        self.setCentralWidget(setup)
        compact_widget(setup, margin=6, spacing=4)

    def _on_completed(self, settings: AppSettings) -> None:
        self._confirmed = True
        self.setup_finished.emit(settings)
        self.close()

    def closeEvent(self, event) -> None:
        if not self._confirmed:
            QApplication.instance().quit()
        super().closeEvent(event)


def _load_app_icon() -> QIcon | None:
    assets = get_bundle_root() / "assets"
    for name in ("icon.ico", "icon.png"):
        path = assets / name
        if path.is_file():
            return QIcon(str(path))
    return None


def run_app() -> None:
    from core.config.paths import ensure_user_data_dir

    ensure_user_data_dir()
    app = QApplication(sys.argv)
    apply_app_theme(app)
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
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
        first_run_settings = settings_manager.load()
        if not first_run_settings.language_selected:
            lang_dlg = _LanguageSelectDialog()
            if lang_dlg.exec() != QDialog.DialogCode.Accepted:
                sys.exit(0)
            chosen = lang_dlg.selected_language()
            first_run_settings.language = chosen
            first_run_settings.language_selected = True
            settings_manager.save(first_run_settings)
            if chosen != "ko":
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)
        setup_window = _SetupWindow(settings_manager)
        setup_window.setup_finished.connect(show_main)
        setup_window.show()

    sys.exit(app.exec())
