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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, SettingsManager
from core.i18n import tr
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import CachedPrediction, PredictionStore
from core.stats.aggregator import Aggregator
from core.stats.player_display import best_display_name
from gui.theme import RED_TEXT, TEXT_SECONDARY, hint_style
from gui.widgets.card_panel import CardPanel
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import dashboard_milestone_color
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


class DashboardView(QWidget):
    import_finished = pyqtSignal(str)
    navigate_to_milestone = pyqtSignal(dict)
    navigate_to_predict = pyqtSignal(int, str)
    navigate_to_initial_import = pyqtSignal()

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

        self.banner = ErrorBanner(self)

        title = QLabel(tr("⚡ OOTP Simulation Control Panel"))
        title.setObjectName("pageTitle")
        self.status_label = QLabel()
        self.status_label.setObjectName("mutedLabel")

        self.import_button = QPushButton(tr("📥  Import Boxscores"))
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self.start_import)
        self.mlb_only_checkbox = QCheckBox(tr("MLB Only"))
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.init_tab_button = QPushButton(tr("→ Initial Setup"))
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
        header_right.addWidget(self.init_tab_button)

        header_row = QHBoxLayout()
        header_row.addLayout(header_left, stretch=1)
        header_row.addLayout(header_right)

        control_card = CardPanel()
        control_card.content_layout.addLayout(header_row)

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
        self.recent_more = QPushButton(tr("View All Milestone Records →"))
        self.recent_more.setObjectName("linkButton")
        self.recent_more.clicked.connect(self._show_all_milestones)
        recent_card = CardPanel(
            tr("🏆  Recent Milestones (last 10)"),
            trailing=self.recent_more,
        )
        recent_card.add_widget(self.recent_list)

        self.near_list = QListWidget()
        self.near_list.itemClicked.connect(self._on_near_clicked)
        self.near_more = QPushButton(tr("View All Predictions →"))
        self.near_more.setObjectName("linkButton")
        self.near_more.clicked.connect(self._show_all_predictions)
        near_card = CardPanel(
            tr("🔥  Upcoming (Near)"),
            trailing=self.near_more,
        )
        near_card.add_widget(self.near_list)

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
        layout.addWidget(self.progress_card)
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

    def refresh(self) -> None:
        self.refresh_recent_achievements()
        self.refresh_near_predictions()
        self.update_status_summary()

    def update_status_summary(self) -> None:
        league = self.settings.active_save or tr("(No league selected)")
        last_import = self.settings.import_state.get("last_import_at", "")
        last_label = last_import[:10] if last_import else "-"
        self.status_label.setText(
            tr("Active League: {league}  ·  Season {season}  ·  Last import: {last}").format(
                league=league, season=self.settings.current_season, last=last_label
            )
        )

    def refresh_recent_achievements(self) -> None:
        self._recent_records = self.aggregator.get_recent_milestone_records(10)
        self.recent_list.clear()
        if not self._recent_records:
            item = QListWidgetItem(tr("No recent milestone records."))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(Qt.GlobalColor.lightGray)
            self.recent_list.addItem(item)
            return
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
            text = f"{name}  ·  {label}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(text)
            item.setSizeHint(QSize(0, 32))
            if is_injury:
                item.setForeground(QColor(RED_TEXT))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item.setForeground(QColor(dashboard_milestone_color(grade)))
            self.recent_list.addItem(item)

    def refresh_near_predictions(self) -> None:
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
        self.near_list.clear()
        if not self._near_predictions:
            item = QListWidgetItem(tr("No near career milestones."))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.near_list.addItem(item)
            return
        for pred in self._near_predictions:
            remaining = int(pred.remaining)
            text = (
                f"🔥 {pred.player_name}\n"
                + tr("   {label} — {remaining:,} remaining").format(
                    label=pred.milestone_label, remaining=remaining
                )
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, pred)
            self.near_list.addItem(item)

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
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
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
        self.progress_card.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        result = payload.batch
        parts = [tr("{count} games added").format(count=result.imported)]
        if result.skipped_non_mlb:
            parts.append(tr("{count} non-MLB skipped").format(count=result.skipped_non_mlb))
        if payload.milestones_recorded:
            parts.append(tr("{count} milestones achieved").format(count=payload.milestones_recorded))
        message = " · ".join(parts)
        self.import_finished.emit(message)
        self.update_status_summary()
        self.refresh()

        if result.errors:
            self.banner.show_warning(
                tr("Some errors: {count} — ").format(count=len(result.errors))
                + (result.errors[0].error if result.errors else "")
            )
        elif payload.milestones:
            box = QMessageBox(self)
            box.setWindowTitle(tr("Import Complete"))
            box.setText(message)
            detail_button = box.addButton(tr("Details"), QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() == detail_button:
                MilestoneAchievedDialog(payload.milestones, self).exec()

    def _on_import_error(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.progress_card.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_error(tr("Import failed: {message}").format(message=message))
