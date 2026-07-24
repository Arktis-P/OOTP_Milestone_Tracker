"""Dashboard tab — recent achievements, near predictions, quick actions."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_state import get_dashboard_import_states, get_readiness_items
from core.config import AppSettings, SettingsManager
from core.i18n import format_relative_datetime, format_full_datetime, tr
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import CachedPrediction, PredictionStore
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter
from core.stats.player_display import best_display_name
from core.streak.read_model import ActiveStreak, list_active_streaks
from gui.theme import RED_TEXT, TEXT_SECONDARY, hint_style
from gui.widgets.card_panel import CardPanel
from gui.widgets.empty_state import EmptyStateWidget
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import dashboard_milestone_color
from gui.widgets.import_errors_dialog import ImportErrorsDialog
from gui.widgets.import_result import build_import_message, show_import_result_banner
from gui.widgets.import_workflow_status import WorkflowStatusPanel, WorkflowStep
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.readiness_checklist import ReadinessChecklistCard
from gui.widgets.streak_center_dialog import StreakCenterDialog
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


def _count_new_files(directory: str, since_epoch: float | None, pattern: str = "*.html") -> int:
    """Count files matching ``pattern`` newer than ``since_epoch``.

    Returns -1 if the folder does not exist or cannot be read, so callers can
    tell "checked, nothing new" (0) apart from "could not check" (-1). This is
    a live filesystem check (not persisted state) so it reflects files that
    appeared after the last recorded import run.
    """
    if not directory or not os.path.isdir(directory):
        return -1
    try:
        count = 0
        for entry in Path(directory).glob(pattern):
            if not entry.is_file():
                continue
            if since_epoch is None or entry.stat().st_mtime > since_epoch:
                count += 1
        return count
    except OSError:
        return -1


def _count_message_files(active_save_path: str) -> int:
    """Count messages/messageN.txt files under the active save's known layouts.

    Returns -1 if no message folder could be located at all (as opposed to 0,
    a message folder that is simply empty right now).
    """
    if not active_save_path:
        return -1
    save_root = Path(active_save_path)
    candidates = [
        save_root / "news" / "html" / "messages",
        save_root / "messages",
        save_root / "news" / "messages",
    ]
    total = 0
    found = False
    for directory in candidates:
        if directory.is_dir():
            found = True
            total += sum(1 for _ in directory.glob("message*.txt"))
    return total if found else -1


class DashboardView(QWidget):
    import_finished = pyqtSignal(str)
    navigate_to_milestone = pyqtSignal(dict)
    navigate_to_predict = pyqtSignal(int, str)
    navigate_to_initial_import = pyqtSignal()
    navigate_to_import_center = pyqtSignal()
    navigate_to_settings = pyqtSignal()
    navigate_to_review_filter = pyqtSignal(str)

    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        settings_manager: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.settings_manager = settings_manager
        self._import_worker: ImportWorker | None = None
        self._recent_records: list[dict] = []
        self._near_predictions: list[CachedPrediction] = []
        self._active_streaks: list[ActiveStreak] = []

        self.banner = ErrorBanner(self)

        title = QLabel(tr("⚡ OOTP Simulation Control Panel"))
        title.setObjectName("pageTitle")
        self.status_label = QLabel()
        self.status_label.setObjectName("mutedLabel")

        self.import_button = QPushButton(tr("📥  Import Boxscores"))
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self.start_import)
        self.cancel_import_button = QPushButton(tr("Cancel"))
        self.cancel_import_button.clicked.connect(self._cancel_import)
        self.cancel_import_button.setVisible(False)
        self.mlb_only_checkbox = QCheckBox(tr("MLB Only"))
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.init_tab_button = QPushButton(tr("→ Import Existing Records"))
        self.init_tab_button.setObjectName("linkButton")

        self.init_tab_button.clicked.connect(self.navigate_to_initial_import.emit)

        header_left = QVBoxLayout()
        header_left.setSpacing(2)
        header_left.addWidget(title)
        header_left.addWidget(self.status_label)

        header_right = QHBoxLayout()
        header_right.setSpacing(8)
        header_right.addWidget(self.mlb_only_checkbox)
        header_right.addWidget(self.import_button)
        header_right.addWidget(self.cancel_import_button)
        header_right.addWidget(self.init_tab_button)

        header_row = QHBoxLayout()
        header_row.addLayout(header_left, stretch=1)
        header_row.addLayout(header_right)

        control_card = CardPanel()
        control_card.content_layout.addLayout(header_row)

        self.readiness_card = ReadinessChecklistCard()
        self.readiness_card.action_requested.connect(self._on_readiness_action)
        self.workflow_panel = WorkflowStatusPanel(
            tr("Import Workflow Status"),
            tr("Use this panel to decide the next safe action before records are changed."),
            self._build_workflow_steps(),
        )
        self.workflow_panel.action_requested.connect(self._on_workflow_action)
        self.workflow_panel.target_requested.connect(self._on_workflow_target)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        self.progress_card = CardPanel()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_label, stretch=1)
        progress_row.addWidget(self.progress_bar, stretch=2)
        self.progress_card.content_layout.addLayout(progress_row)
        self.progress_card.setVisible(False)

        self.recent_list = QListWidget()
        self.recent_list.setObjectName("dashboardMilestoneList")
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        self.recent_empty = EmptyStateWidget()
        self.recent_stack = QStackedWidget()
        self.recent_stack.addWidget(self.recent_list)
        self.recent_stack.addWidget(self.recent_empty)
        self.recent_more = QPushButton(tr("View All Achievement Records →"))
        self.recent_more.setObjectName("linkButton")
        self.recent_more.clicked.connect(self._show_all_milestones)
        recent_card = CardPanel(
            tr("🏆  Recent Milestones (last 10)"),
            trailing=self.recent_more,
        )
        recent_card.add_widget(self.recent_stack)

        self.near_list = QListWidget()
        self.near_list.itemClicked.connect(self._on_near_clicked)
        self.near_empty = EmptyStateWidget()
        self.near_stack = QStackedWidget()
        self.near_stack.addWidget(self.near_list)
        self.near_stack.addWidget(self.near_empty)
        self.near_more = QPushButton(tr("View All Predictions →"))
        self.near_more.setObjectName("linkButton")
        self.near_more.clicked.connect(self._show_all_predictions)
        near_card = CardPanel(
            tr("🔥  Upcoming (Near)"),
            trailing=self.near_more,
        )
        near_card.add_widget(self.near_stack)

        self.streak_list = QListWidget()
        self.streak_empty = EmptyStateWidget()
        self.streak_stack = QStackedWidget()
        self.streak_stack.addWidget(self.streak_list)
        self.streak_stack.addWidget(self.streak_empty)
        self.streak_more = QPushButton(tr("View Ended Streaks"))
        self.streak_more.setObjectName("linkButton")
        self.streak_more.clicked.connect(self._show_ended_streaks)
        streak_card = CardPanel(
            tr("Active Streaks"),
            trailing=self.streak_more,
        )
        streak_sort_hint = QLabel(
            tr("Most recent success first; values are not ranked across streak types.")
        )
        streak_sort_hint.setStyleSheet(hint_style(TEXT_SECONDARY))
        streak_card.add_widget(streak_sort_hint)
        streak_card.add_widget(self.streak_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(recent_card)
        splitter.addWidget(near_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(control_card)
        layout.addWidget(self.readiness_card)
        layout.addWidget(self.workflow_panel)
        layout.addWidget(self.progress_card)
        layout.addWidget(streak_card, stretch=1)
        layout.addWidget(splitter, stretch=1)

        self.update_status_summary()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def on_data_refreshed(self, kind: str) -> None:
        if kind in ("boxscore", "milestone", "all"):
            self.refresh_recent_achievements()
        if kind in ("boxscore", "init", "milestone", "all"):
            self.refresh_near_predictions()
        if kind in ("boxscore", "init", "milestone", "all", "settings"):
            self.update_status_summary()
            self.refresh_active_streaks()

    def refresh(self) -> None:
        self.refresh_recent_achievements()
        self.refresh_near_predictions()
        self.refresh_active_streaks()
        self.update_status_summary()

    def refresh_active_streaks(self) -> None:
        self.streak_list.clear()
        self._active_streaks = []
        if self.aggregator.is_closed:
            self._show_active_streak_empty(
                tr("Active streaks are unavailable."),
                tr("Open a league database to view current streaks."),
            )
            return
        try:
            self._active_streaks = list_active_streaks(
                self.aggregator,
                self.settings.current_season,
                limit=8,
            )
        except Exception:
            self._show_active_streak_empty(
                tr("Active streaks could not be loaded."),
                tr("The database may be unavailable. Try refreshing after reopening the league."),
            )
            return
        if not self._active_streaks:
            self._show_active_streak_empty(
                tr("No active streaks."),
                tr("Import boxscores to detect streaks currently in progress."),
            )
            return

        self.streak_stack.setCurrentWidget(self.streak_list)
        for streak in self._active_streaks:
            date_parts = [part for part in (streak.start_date, streak.last_date) if part]
            date_text = " → ".join(date_parts) if date_parts else tr("Date unavailable")
            item = QListWidgetItem(
                f"{streak.player_name}  ·  {streak.team}  ·  {streak.label}"
                f"  ·  {streak.display_value} {tr(streak.unit)}\n{date_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, streak)
            item.setToolTip(item.text())
            item.setSizeHint(QSize(0, 44))
            self.streak_list.addItem(item)

    def _show_active_streak_empty(self, title: str, subtitle: str) -> None:
        self.streak_empty.set_content(
            "🔥",
            title,
            subtitle,
            [(tr("View Ended Streaks"), self._show_ended_streaks)],
        )
        self.streak_stack.setCurrentWidget(self.streak_empty)

    def update_status_summary(self) -> None:
        league = self.settings.active_save or tr("(No league selected)")
        last_import = self.settings.import_state.get("last_import_at", "")
        last_label = format_relative_datetime(last_import)
        self.status_label.setText(
            tr("Active League: {league}  ·  Season {season}  ·  Last import: {last}").format(
                league=league, season=self.settings.current_season, last=last_label
            )
        )
        self.status_label.setToolTip(format_full_datetime(last_import))
        if not self.aggregator.is_closed:
            self.readiness_card.set_items(
                get_readiness_items(self.settings, self.aggregator)
            )
        self.workflow_panel.set_steps(self._build_workflow_steps())

    def _build_workflow_steps(self) -> list[WorkflowStep]:
        persisted = {
            item.key: item
            for item in get_dashboard_import_states(self.settings, self.aggregator)
        }
        latest = persisted["latest_boxscores"]
        news = persisted["news_messages"]
        baseline = persisted["baseline_history"]
        season = persisted["season_finalize"]

        def workflow_status(item) -> str:
            state = item.workflow
            if state.outcome == "completed":
                return "complete"
            if state.outcome in ("partial_success", "failed"):
                return "warning"
            if state.is_running:
                return "running"
            return "needed" if item.actionable else "warning"

        def last_run(item) -> str:
            timestamp = item.workflow.completed_at or item.workflow.started_at or ""
            return format_relative_datetime(timestamp)

        league_status, league_reason, league_route = self._league_tracking_state()
        (
            baseline_status,
            baseline_last_run,
            baseline_reason,
            baseline_action,
            baseline_target,
            baseline_route,
        ) = self._baseline_history_state(baseline, last_run(baseline))
        (
            boxscore_status,
            boxscore_reason,
            boxscore_action,
            boxscore_target,
            boxscore_route,
            boxscore_pending,
        ) = self._latest_boxscores_state(latest, workflow_status(latest))
        (
            news_status,
            news_reason,
            news_action,
            news_target,
            news_route,
        ) = self._news_messages_state(news, workflow_status(news))
        (
            unresolved_status,
            unresolved_reason,
            unresolved_route,
        ) = self._unresolved_items_state(persisted, boxscore_pending)
        (
            season_status,
            season_action,
            season_target,
            season_route,
        ) = self._season_finalize_state(season, workflow_status(season))

        self._step_routes = {
            "league_tracking": league_route,
            "baseline_records": baseline_route,
            "latest_boxscores": boxscore_route,
            "news_messages": news_route,
            "record_exceptions": unresolved_route,
            "season_finalize": season_route,
        }

        return [
            WorkflowStep(
                "league_tracking",
                tr("Check tracked league and teams"),
                league_status,
                last_run=tr("Current settings"),
                reason=league_reason,
                action_label=tr("Open settings"),
                target_label=tr("Settings"),
            ),
            WorkflowStep(
                "baseline_records",
                tr("Confirm career baseline is current"),
                baseline_status,
                last_run=baseline_last_run,
                reason=baseline_reason,
                action_label=baseline_action,
                target_label=baseline_target,
            ),
            WorkflowStep(
                "latest_boxscores",
                tr("Import latest boxscores"),
                boxscore_status,
                last_run=last_run(latest),
                reason=boxscore_reason,
                action_label=boxscore_action,
                target_label=boxscore_target,
            ),
            WorkflowStep(
                "news_messages",
                tr("Scan and review news messages"),
                news_status,
                last_run=last_run(news),
                reason=news_reason,
                action_label=news_action,
                target_label=news_target,
            ),
            WorkflowStep(
                "record_exceptions",
                tr("Review ties, exclusions, missing dates, and errors"),
                unresolved_status,
                last_run=max((last_run(item) for item in persisted.values()), default=""),
                reason=unresolved_reason,
                action_label=tr("Review records"),
                target_label=tr("Achievement records"),
            ),
            WorkflowStep(
                "season_finalize",
                tr("Finalize season-end records"),
                season_status,
                last_run=last_run(season),
                reason=season.detail,
                action_label=season_action,
                target_label=season_target,
            ),
        ]

    def _league_tracking_state(self) -> tuple[str, str, str]:
        league_ready = bool(self.settings.active_save)
        teams_ready = bool(self.settings.tracked_teams)
        save_path = getattr(self.settings, "active_save_path", "") or ""
        path_ok = bool(save_path) and os.path.isdir(save_path)
        if not league_ready:
            return "needed", tr("Select a league before importing records."), "settings"
        if not teams_ready:
            return "warning", tr("Select tracked teams to narrow milestone tracking."), "settings"
        if save_path and not path_ok:
            return "warning", tr("The saved league path is no longer accessible."), "settings"
        return "complete", tr("A league is selected."), "settings"

    def _baseline_history_state(
        self, item, persisted_last_run: str
    ) -> tuple[str, str, str, str, str, str]:
        if self.aggregator.is_closed:
            return (
                "needed",
                persisted_last_run,
                tr("Open a league database, then import career and historical stats."),
                tr("Import baseline"),
                tr("Import center"),
                "import",
            )
        summary = InitialImporter(self.aggregator).get_init_summary()
        loaded = bool(summary["batting_players"] or summary["pitching_players"])
        coverage = int(summary.get("season_coverage") or 0)
        if not loaded:
            return (
                "needed",
                persisted_last_run,
                tr("Import career and historical stats before relying on predictions."),
                tr("Import baseline"),
                tr("Import center"),
                "import",
            )
        last_run = summary.get("last_refreshed_at") or summary.get("batting_imported_at") or persisted_last_run
        if coverage and coverage < self.settings.current_season:
            return (
                "warning",
                format_relative_datetime(last_run) if last_run else persisted_last_run,
                tr("Baseline data predates the current season; refresh recommended."),
                tr("Refresh baseline"),
                tr("Import center"),
                "import",
            )
        return (
            "complete",
            format_relative_datetime(last_run) if last_run else persisted_last_run,
            tr("Through {season} season · {batting:,} batters / {pitching:,} pitchers").format(
                season=coverage, batting=summary["batting_players"], pitching=summary["pitching_players"],
            ),
            tr("View coverage"),
            tr("Import center"),
            "results",
        )

    def _latest_boxscores_state(self, item, base_status: str) -> tuple[str, str, str, str, str, int]:
        boxscore_dir = self.settings.boxscore_dir
        if not boxscore_dir:
            return "warning", tr("Configure the boxscore folder first."), tr("Open settings"), tr("Settings"), "settings", -1
        get_last_import = getattr(
            self.settings_manager, "get_last_boxscore_import_at", None
        )
        since_epoch = (
            get_last_import(self.settings, boxscore_dir)
            if callable(get_last_import)
            else None
        )
        pending = _count_new_files(boxscore_dir, since_epoch)
        if pending < 0:
            return (
                "warning",
                tr("The configured boxscore folder could not be read."),
                tr("Open settings"),
                tr("Settings"),
                "settings",
                pending,
            )
        if pending > 0:
            return (
                "needed",
                tr("{count} new boxscore file(s) are ready to import.").format(count=pending),
                tr("Import boxscores"),
                tr("Import center"),
                "import",
                pending,
            )
        if base_status == "warning":
            return (
                "warning",
                item.detail,
                tr("Check errors"),
                tr("Errors"),
                "filter:latest_boxscores",
                pending,
            )
        return (
            "complete" if base_status == "complete" else base_status,
            item.detail,
            tr("View results"),
            tr("Achievement records"),
            "results",
            pending,
        )

    def _news_messages_state(self, item, base_status: str) -> tuple[str, str, str, str, str]:
        save_path = getattr(self.settings, "active_save_path", "") or ""
        total = _count_message_files(save_path)
        unresolved = item.workflow.unresolved or {}
        if unresolved.get("date_missing"):
            return (
                "warning",
                tr("{count} message(s) are missing a date.").format(count=unresolved["date_missing"]),
                tr("Open date-missing filter"),
                tr("Missing dates"),
                "filter:date_missing",
            )
        if unresolved.get("errors"):
            return (
                "warning",
                tr("{count} message(s) could not be parsed.").format(count=unresolved["errors"]),
                tr("Check errors"),
                tr("Errors"),
                "filter:message_errors",
            )
        if total < 0:
            return (
                "needed" if not save_path else base_status,
                tr("Select a league to locate message files.") if not save_path else tr("No message folder was found for this league."),
                tr("Open review"),
                tr("Import center"),
                "review",
            )
        if total == 0:
            return (
                "complete",
                tr("There are currently no news messages to review."),
                tr("Open review"),
                tr("Import center"),
                "results",
            )
        if base_status == "complete":
            return "complete", item.detail, tr("View results"), tr("Import center"), "results"
        return (
            "needed",
            tr("{count} message file(s) are ready to review.").format(count=total),
            tr("Open review"),
            tr("Import center"),
            "review",
        )

    def _unresolved_items_state(self, persisted: dict, boxscore_pending: int) -> tuple[str, str, str]:
        issues: dict[str, int] = {}
        for key, item in persisted.items():
            for reason, count in (item.workflow.unresolved or {}).items():
                if count:
                    issues[f"{key}:{reason}"] = issues.get(f"{key}:{reason}", 0) + int(count)
        if boxscore_pending < 0:
            issues["latest_boxscores:folder"] = issues.get("latest_boxscores:folder", 0) + 1
        total = sum(issues.values())
        if total == 0:
            return "complete", tr("No unresolved import items."), "results"
        primary_key = max(issues, key=issues.get)
        return (
            "warning",
            tr("{count} unresolved import items need review.").format(count=total),
            f"filter:{primary_key.split(':', 1)[0]}",
        )

    def _season_finalize_state(self, item, base_status: str) -> tuple[str, str, str, str]:
        if item.workflow.outcome == "completed":
            return "complete", tr("View results"), tr("Import center"), "results"
        return base_status, tr("Finalize"), tr("Import center"), "import"

    def _on_workflow_action(self, key: str) -> None:
        self._dispatch_workflow_route(key)

    def _on_workflow_target(self, key: str) -> None:
        self._dispatch_workflow_route(key)

    def _dispatch_workflow_route(self, key: str) -> None:
        route = getattr(self, "_step_routes", {}).get(key, "")
        if route == "settings":
            self.navigate_to_settings.emit()
            return
        if route == "import" and key == "latest_boxscores":
            self.start_import()
            return
        if route == "results":
            self.navigate_to_milestone.emit({})
            return
        if route.startswith("filter:"):
            self.navigate_to_review_filter.emit(route.split(":", 1)[1])
            return
        self.navigate_to_import_center.emit()

    def _on_readiness_action(self, key: str) -> None:
        if key in ("league", "teams"):
            self.navigate_to_settings.emit()
        elif key == "init_import":
            self.navigate_to_initial_import.emit()
        elif key == "boxscore_import":
            self.start_import()

    def refresh_recent_achievements(self) -> None:
        self.recent_list.clear()
        if self.aggregator.is_closed:
            self._recent_records = []
            self.recent_empty.set_content(
                "🏆",
                tr("Milestone records are unavailable."),
                tr("Open a league database and try again."),
            )
            self.recent_stack.setCurrentWidget(self.recent_empty)
            return
        self._recent_records = self.aggregator.get_recent_milestone_records(10)
        if not self._recent_records:
            self.recent_empty.set_content(
                "🏆",
                tr("No recent milestone records."),
                tr("Import boxscores to automatically detect milestones."),
                [
                    (tr("Import Boxscores"), self.start_import),
                    (tr("Go to Achievement Records"), self._show_all_milestones),
                ],
            )
            self.recent_stack.setCurrentWidget(self.recent_empty)
            return
        self.recent_stack.setCurrentWidget(self.recent_list)
        for record in self._recent_records:
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = (
                milestone.label
                if milestone
                else record.get("milestone_label", record["milestone_key"])
            )
            grade = milestone.grade if milestone else "common"
            if int(record.get("player_id") or 0) == 0:
                name = record.get("team_display") or record.get("team") or ""
            else:
                name = best_display_name(
                    record.get("full_name"),
                    record.get("short_name"),
                )
            if not name:
                name = record.get("team") or "—"
            is_injury = record.get("milestone_key") == "manual_injury"
            detail_parts = []
            if record.get("achieved_date"):
                detail_parts.append(str(record["achieved_date"]))
            if record.get("opponent_team"):
                detail_parts.append(
                    tr("vs {opponent}").format(opponent=record["opponent_team"])
                )
            if record.get("season"):
                detail_parts.append(
                    tr("{season} season").format(season=record["season"])
                )
            first_line = f"{name}  ·  {label}"
            text = first_line
            if detail_parts:
                text += "\n" + "  ·  ".join(detail_parts)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(text)
            item.setSizeHint(QSize(0, 44 if detail_parts else 32))
            if is_injury:
                item.setForeground(QColor(RED_TEXT))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item.setForeground(QColor(dashboard_milestone_color(grade)))
            self.recent_list.addItem(item)

    def refresh_near_predictions(self) -> None:
        self.near_list.clear()
        if self.aggregator.is_closed:
            self._near_predictions = []
            self.near_empty.set_content(
                "🔮",
                tr("Predictions are unavailable."),
                tr("Open a league database and try again."),
            )
            self.near_stack.setCurrentWidget(self.near_empty)
            return
        store = PredictionStore(
            self.aggregator,
            self.milestones,
            season=self.settings.current_season,
            season_games_total=self.settings.season_games_total,
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        store.ensure_seeded()
        self._near_predictions = store.list_near_cached(limit=10)
        if not self._near_predictions:
            self.near_empty.set_content(
                "🔮",
                tr("No predictable records."),
                tr("Import existing career/season records first."),
                [(tr("Import Existing Records"), self.navigate_to_initial_import.emit)],
            )
            self.near_stack.setCurrentWidget(self.near_empty)
            return
        self.near_stack.setCurrentWidget(self.near_list)
        for pred in self._near_predictions:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, pred)
            item.setSizeHint(QSize(0, 62))
            self.near_list.addItem(item)
            self.near_list.setItemWidget(item, self._build_near_row(pred))

    def _build_near_row(self, pred: CachedPrediction) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(3)

        header = QLabel(f"🔥 {pred.player_name}  ·  {pred.milestone_label}")
        header.setStyleSheet("font-weight: 600;")

        bar = QProgressBar()
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setMaximum(1000)
        bar.setValue(max(0, min(1000, int(pred.progress_pct * 10))))

        detail = QLabel(
            tr("{current:,.0f} / {target:,.0f}  ·  {remaining:,.0f} remaining").format(
                current=pred.current_value,
                target=pred.threshold,
                remaining=pred.remaining,
            )
        )
        detail.setStyleSheet(hint_style(TEXT_SECONDARY))

        layout.addWidget(header)
        layout.addWidget(bar)
        layout.addWidget(detail)
        return row

    def _on_recent_clicked(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self.navigate_to_milestone.emit(record)

    def _on_near_clicked(self, item: QListWidgetItem) -> None:
        pred = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(pred, CachedPrediction):
            self.navigate_to_predict.emit(pred.player_id, pred.milestone_key)

    def _show_all_milestones(self) -> None:
        self.navigate_to_milestone.emit({})

    def _show_ended_streaks(self) -> None:
        if self.aggregator.is_closed:
            QMessageBox.information(
                self,
                tr("Streak Center"),
                tr("Open a league database to view streaks."),
            )
            return
        StreakCenterDialog(
            self.aggregator,
            self.settings.current_season,
            self,
        ).exec()

    def _show_all_predictions(self) -> None:
        self.navigate_to_predict.emit(-1, "")

    def _on_mlb_only_toggled(self, checked: bool) -> None:
        self.settings.import_mlb_only = checked
        self.settings_manager.save(self.settings)

    def start_import(self) -> None:
        self.settings.import_mlb_only = self.mlb_only_checkbox.isChecked()
        boxscore_dir = self.settings.boxscore_dir
        if not boxscore_dir:
            self.banner.show_warning(tr("Boxscore folder not configured. Select a league in Settings."))
            return

        self.import_button.setEnabled(False)
        self.cancel_import_button.setVisible(True)
        self.cancel_import_button.setEnabled(True)
        self.progress_card.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)

        since_mtime = self.settings_manager.get_last_boxscore_import_at(
            self.settings, boxscore_dir
        )
        self._import_worker = ImportWorker(
            self.aggregator.db_path,
            self.settings_manager,
            self.milestones,
            self.settings,
            boxscore_dir,
            self.settings.current_season,
            since_mtime=since_mtime,
            parent=self,
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.completed.connect(self._on_import_finished)
        self._import_worker.cancelled.connect(self._on_import_cancelled)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.finished.connect(
            lambda worker=self._import_worker: self._finish_import_worker(worker)
        )
        self._import_worker.start()

    def _on_import_progress(
        self, current: int, total: int, filename: str, phase: str = "import"
    ) -> None:
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)
        if phase == "milestone":
            self.progress_label.setText(
                tr("Checking milestones... ({current}/{total}) {filename}").format(
                    current=current, total=total, filename=filename
                )
            )
        elif phase == "streak":
            self.progress_label.setText(
                tr("Checking streaks... ({current}/{total}) {filename}").format(
                    current=current, total=total, filename=filename
                )
            )
        else:
            self.progress_label.setText(
                tr("Importing boxscores... ({current}/{total}) {filename}").format(
                    current=current, total=total, filename=filename
                )
            )

    def _on_import_finished(self, payload: ImportFinishedPayload) -> None:
        self.import_button.setEnabled(True)
        self.cancel_import_button.setVisible(False)
        self.progress_card.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        self.import_finished.emit(build_import_message(payload))
        self.update_status_summary()
        self.refresh()

        show_import_result_banner(
            self.banner,
            payload,
            on_view_milestones=lambda: MilestoneAchievedDialog(payload.milestones, self).exec(),
            on_view_errors=lambda: ImportErrorsDialog(payload.batch.errors, self).exec(),
        )

    def _on_import_error(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.cancel_import_button.setVisible(False)
        self.progress_card.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_error(tr("Import failed: {message}").format(message=message))

    def _on_import_cancelled(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.cancel_import_button.setVisible(False)
        self.progress_card.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_info(message)

    def _cancel_import(self) -> None:
        if self._import_worker and self._import_worker.isRunning():
            self.cancel_import_button.setEnabled(False)
            self.progress_label.setText(tr("Cancelling import after the current item..."))
            self._import_worker.cancel()

    def _finish_import_worker(self, worker: ImportWorker) -> None:
        if self._import_worker is worker:
            self._import_worker = None
        worker.deleteLater()
