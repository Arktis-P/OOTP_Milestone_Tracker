"""Dashboard tab — recent achievements, near predictions, quick actions."""

from __future__ import annotations

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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_state import get_readiness_items
from core.config import AppSettings, SettingsManager
from core.i18n import format_relative_datetime, format_full_datetime, tr
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import CachedPrediction, PredictionStore
from core.stats.aggregator import Aggregator
from core.stats.player_display import best_display_name
from core.streak.read_model import ActiveStreak, list_active_streaks
from gui.theme import RED_TEXT, TEXT_SECONDARY, hint_style
from gui.widgets.card_panel import CardPanel
from gui.widgets.empty_state import EmptyStateWidget
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import dashboard_milestone_color
from gui.widgets.import_result import build_import_message, show_import_result_banner
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.readiness_checklist import ReadinessChecklistCard
from gui.widgets.streak_center_dialog import StreakCenterDialog
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


class DashboardView(QWidget):
    import_finished = pyqtSignal(str)
    navigate_to_milestone = pyqtSignal(dict)
    navigate_to_predict = pyqtSignal(int, str)
    navigate_to_initial_import = pyqtSignal()
    navigate_to_settings = pyqtSignal()

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

        title = QLabel(tr("OOTP Command Center"))
        title.setObjectName("pageTitle")
        title.setWordWrap(True)
        subtitle = QLabel(
            tr("Import boxscores and review the records that need attention now.")
        )
        subtitle.setObjectName("helperText")
        subtitle.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)

        self.import_button = QPushButton(tr("Import Boxscores"))
        self.import_button.setObjectName("primaryButton")
        self.import_button.setMinimumWidth(150)
        self.import_button.clicked.connect(self.start_import)
        self.cancel_import_button = QPushButton(tr("Cancel"))
        self.cancel_import_button.clicked.connect(self._cancel_import)
        self.cancel_import_button.setVisible(False)
        self.mlb_only_checkbox = QCheckBox(tr("MLB Only"))
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.init_tab_button = QPushButton(tr("Import Existing Records"))
        self.init_tab_button.setObjectName("linkButton")

        self.init_tab_button.clicked.connect(self.navigate_to_initial_import.emit)

        header_left = QVBoxLayout()
        header_left.setSpacing(4)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_left.addWidget(self.status_label)

        header_right = QVBoxLayout()
        header_right.setSpacing(8)
        cta_row = QHBoxLayout()
        cta_row.setSpacing(8)
        cta_row.addWidget(self.import_button)
        cta_row.addWidget(self.cancel_import_button)
        header_right.addLayout(cta_row)
        header_right.addWidget(self.init_tab_button, alignment=Qt.AlignmentFlag.AlignRight)
        header_right.addWidget(self.mlb_only_checkbox, alignment=Qt.AlignmentFlag.AlignRight)

        header_row = QHBoxLayout()
        header_row.setSpacing(18)
        header_row.addLayout(header_left, stretch=1)
        header_row.addLayout(header_right)

        control_card = CardPanel()
        control_card.setObjectName("dashboardHero")
        control_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        control_card.setStyleSheet(
            """
            QFrame#dashboardHero {
                background-color: #202326;
                border: 1px solid #454a50;
                border-radius: 14px;
            }
            QFrame#dashboardHero QLabel#pageTitle {
                color: #f2f5f8;
                font-size: 20px;
                font-weight: 750;
                min-height: 34px;
            }
            QFrame#dashboardHero QLabel#helperText {
                color: #aab4be;
                font-size: 12px;
            }
            QFrame#dashboardHero QLabel#statusText {
                color: #d0d6dc;
                font-size: 12px;
            }
            """
        )
        control_card.content_layout.addLayout(header_row)

        self.readiness_card = ReadinessChecklistCard()
        self.readiness_card.action_requested.connect(self._on_readiness_action)

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
        self.recent_list.setWordWrap(True)
        self.recent_list.setSpacing(2)
        self.recent_list.setStyleSheet("QListWidget { background: transparent; border: none; }")
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        self.recent_empty = EmptyStateWidget()
        self.recent_stack = QStackedWidget()
        self.recent_stack.addWidget(self.recent_list)
        self.recent_stack.addWidget(self.recent_empty)
        self.recent_more = QPushButton(tr("View All"))
        self.recent_more.setObjectName("linkButton")
        self.recent_more.clicked.connect(self._show_all_milestones)
        recent_card = CardPanel(
            tr("Recent Achievements"),
            trailing=self.recent_more,
        )
        recent_card.setObjectName("dashboardSectionCard")
        recent_card.add_widget(self.recent_stack)

        self.near_list = QListWidget()
        self.near_list.setObjectName("dashboardNearList")
        self.near_list.setWordWrap(True)
        self.near_list.setSpacing(2)
        self.near_list.setStyleSheet("QListWidget { background: transparent; border: none; }")
        self.near_list.itemClicked.connect(self._on_near_clicked)
        self.near_empty = EmptyStateWidget()
        self.near_stack = QStackedWidget()
        self.near_stack.addWidget(self.near_list)
        self.near_stack.addWidget(self.near_empty)
        self.near_more = QPushButton(tr("View Predictions"))
        self.near_more.setObjectName("linkButton")
        self.near_more.clicked.connect(self._show_all_predictions)
        near_card = CardPanel(
            tr("Milestone Watch"),
            trailing=self.near_more,
        )
        near_card.setObjectName("dashboardSectionCard")
        near_card.add_widget(self.near_stack)

        self.streak_list = QListWidget()
        self.streak_list.setObjectName("dashboardStreakList")
        self.streak_list.setWordWrap(True)
        self.streak_list.setSpacing(2)
        self.streak_list.setStyleSheet("QListWidget { background: transparent; border: none; }")
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
        streak_card.setObjectName("dashboardSectionCard")
        streak_card.setMaximumHeight(270)
        streak_sort_hint = QLabel(
            tr("Recent success order. Values are not ranked across streak types.")
        )
        streak_sort_hint.setObjectName("helperText")
        streak_sort_hint.setWordWrap(True)
        streak_sort_hint.setStyleSheet(hint_style(TEXT_SECONDARY))
        streak_card.add_widget(streak_sort_hint)
        streak_card.add_widget(self.streak_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("dashboardSplitter")
        splitter.addWidget(recent_card)
        splitter.addWidget(near_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([1, 1])

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(control_card)
        layout.addWidget(self.readiness_card)
        layout.addWidget(self.progress_card)
        layout.addWidget(streak_card)
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
                limit=6,
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
            title = f"{streak.player_name} · {streak.team}"
            metric = f"{streak.display_value} {tr(streak.unit)}"
            detail = f"{streak.label} · {date_text}"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, streak)
            item.setToolTip(f"{title}\n{metric} · {detail}")
            item.setSizeHint(QSize(0, 58))
            self.streak_list.addItem(item)
            self.streak_list.setItemWidget(
                item,
                self._build_dashboard_row(
                    title,
                    detail,
                    badge=metric,
                    accent="#75beff",
                ),
            )

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
            title = f"{name} · {label}"
            text = title
            if detail_parts:
                text += "\n" + "  ·  ".join(detail_parts)
            detail = " · ".join(detail_parts)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(text)
            item.setSizeHint(QSize(0, 58 if detail_parts else 50))
            self.recent_list.addItem(item)
            row = self._build_dashboard_row(
                title,
                detail,
                badge=tr("Milestone"),
                accent=RED_TEXT if is_injury else dashboard_milestone_color(grade),
            )
            if is_injury:
                item.setForeground(QColor(RED_TEXT))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item.setForeground(QColor(dashboard_milestone_color(grade)))
            self.recent_list.setItemWidget(item, row)

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
            item.setSizeHint(QSize(0, 70))
            self.near_list.addItem(item)
            self.near_list.setItemWidget(item, self._build_near_row(pred))

    def _build_near_row(self, pred: CachedPrediction) -> QWidget:
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QLabel(f"{pred.player_name} · {pred.milestone_label}")
        header.setObjectName("playerName")
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: 600;")

        bar = QProgressBar()
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setMaximum(1000)
        bar.setValue(max(0, min(1000, int(pred.progress_pct * 10))))

        detail = QLabel(
            tr("{current:,.0f} of {target:,.0f} · {remaining:,.0f} left").format(
                current=pred.current_value,
                target=pred.threshold,
                remaining=pred.remaining,
            )
        )
        detail.setObjectName("helperText")
        detail.setWordWrap(True)
        detail.setStyleSheet(hint_style(TEXT_SECONDARY))

        layout.addWidget(header)
        layout.addWidget(bar)
        layout.addWidget(detail)
        return row

    def _build_dashboard_row(
        self,
        title: str,
        detail: str,
        *,
        badge: str,
        accent: str,
    ) -> QWidget:
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("playerName")
        title_label.setWordWrap(True)
        detail_label = QLabel(detail or " ")
        detail_label.setObjectName("helperText")
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        text_col.addWidget(title_label)
        text_col.addWidget(detail_label)
        layout.addLayout(text_col, stretch=1)

        badge_label = QLabel(badge)
        badge_label.setObjectName("secondaryStat")
        badge_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        badge_label.setMinimumWidth(72)
        badge_label.setStyleSheet(
            f"color: {accent}; font-weight: 700; padding-left: 8px;"
        )
        layout.addWidget(badge_label)
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
            on_view_error=lambda: QMessageBox.warning(
                self,
                tr("Import Errors"),
                payload.batch.errors[0].error if payload.batch.errors else "",
            ),
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
