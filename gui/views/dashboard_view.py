"""Dashboard tab — recent achievements, near predictions, quick actions."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
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
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.prediction_store import CachedPrediction, PredictionStore
from core.stats.aggregator import Aggregator
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.grade_styles import apply_grade_to_list_item
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

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #9CA3AF; padding: 4px 0;")

        self.import_button = QPushButton("박스스코어 가져오기")
        self.import_button.clicked.connect(self.start_import)
        self.mlb_only_checkbox = QCheckBox("MLB만")
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.init_tab_button = QPushButton("초기값 설정으로")
        self.init_tab_button.clicked.connect(self.navigate_to_initial_import.emit)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        action_row = QHBoxLayout()
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.mlb_only_checkbox)
        action_row.addWidget(self.init_tab_button)
        action_row.addWidget(self.progress_label)
        action_row.addWidget(self.progress_bar, stretch=1)

        self.recent_list = QListWidget()
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        recent_box = QGroupBox("최근 달성한 마일스톤 (10건)")
        recent_layout = QVBoxLayout(recent_box)
        recent_layout.addWidget(self.recent_list)
        self.recent_more = QPushButton("마일스톤 기록 전체 보기 →")
        self.recent_more.clicked.connect(self._show_all_milestones)
        recent_layout.addWidget(self.recent_more)

        self.near_list = QListWidget()
        self.near_list.itemClicked.connect(self._on_near_clicked)
        near_box = QGroupBox("곧 달성 예정 (임박)")
        near_layout = QVBoxLayout(near_box)
        near_layout.addWidget(self.near_list)
        self.near_more = QPushButton("예측 탭에서 전체 보기 →")
        self.near_more.clicked.connect(self._show_all_predictions)
        near_layout.addWidget(self.near_more)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(recent_box)
        splitter.addWidget(near_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("대시보드"))
        layout.addWidget(self.status_label)
        layout.addWidget(self.banner)
        layout.addLayout(action_row)
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
        league = self.settings.active_save or "(리그 미선택)"
        last_import = self.settings.import_state.get("last_import_at", "")
        last_label = last_import[:10] if last_import else "-"
        self.status_label.setText(
            f"현재 리그: {league} {self.settings.current_season}   "
            f"마지막 가져오기: {last_label}"
        )

    def refresh_recent_achievements(self) -> None:
        self._recent_records = self.aggregator.get_recent_milestone_records(10)
        self.recent_list.clear()
        if not self._recent_records:
            item = QListWidgetItem("최근 달성 기록이 없습니다.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
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
            name = record.get("display_name") or ""
            if not name and int(record.get("player_id") or 0) == 0:
                name = record.get("team") or ""
            date = (record.get("achieved_date") or "")[:10]
            text = f"🏆 {name}\n   {label} ({date})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record)
            apply_grade_to_list_item(item, grade)
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
            item = QListWidgetItem("임박한 통산 마일스톤이 없습니다.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.near_list.addItem(item)
            return
        for pred in self._near_predictions:
            remaining = int(pred.remaining)
            text = (
                f"🔥 {pred.player_name}\n"
                f"   {pred.milestone_label} — {remaining:,}개 남음"
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
            self.banner.show_warning(
                "박스스코어 폴더가 설정되지 않았습니다. 설정 탭에서 리그를 선택하세요."
            )
            return

        self.import_button.setEnabled(False)
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
                f"마일스톤 확인 중... ({current}/{total}) {filename}"
            )
        elif phase == "streak":
            self.progress_label.setText(
                f"연속기록 확인 중... ({current}/{total}) {filename}"
            )
        else:
            self.progress_label.setText(
                f"박스스코어 가져오는 중... ({current}/{total}) {filename}"
            )

    def _on_import_finished(self, payload: ImportFinishedPayload) -> None:
        self.import_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        result = payload.batch
        parts = [f"{result.imported}경기 추가됨"]
        if result.skipped_non_mlb:
            parts.append(f"MLB 외 {result.skipped_non_mlb}건 스킵")
        if payload.milestones_recorded:
            parts.append(f"마일스톤 {payload.milestones_recorded}건 달성")
        message = " · ".join(parts)
        self.import_finished.emit(message)
        self.update_status_summary()
        self.refresh()

        if result.errors:
            self.banner.show_warning(
                f"일부 오류: {len(result.errors)}건 — "
                f"{result.errors[0].error if result.errors else ''}"
            )
        elif payload.milestones:
            box = QMessageBox(self)
            box.setWindowTitle("가져오기 완료")
            box.setText(message)
            detail_button = box.addButton("자세히 보기", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() == detail_button:
                MilestoneAchievedDialog(payload.milestones, self).exec()

    def _on_import_error(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_error(f"가져오기 실패: {message}")
