"""Player and team statistics tab."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import outs_to_ip_str
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.table_widgets import TablePanel
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


class StatsView(QWidget):
    import_finished = pyqtSignal(str)

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        milestones: MilestoneDefinitions,
        settings_manager: SettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.milestones = milestones
        self.settings_manager = settings_manager or SettingsManager()
        self._import_worker: ImportWorker | None = None

        self.import_button = QPushButton("박스스코어 가져오기")
        self.import_button.clicked.connect(self.start_import)

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["시즌 타격", "통산 타격", "시즌 투구", "통산 투구"])
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(self.import_button)
        controls.addWidget(QLabel("기록 유형:"))
        controls.addWidget(self.scope_combo)
        controls.addStretch()

        self.table_panel = TablePanel(
            ["선수", "팀", "기록"],
            placeholder="선수 검색...",
        )

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.table_panel)

        self.refresh()

    def start_import(self) -> None:
        boxscore_dir = self.settings.boxscore_dir
        if not boxscore_dir:
            QMessageBox.warning(
                self,
                "경로 없음",
                "박스스코어 폴더가 설정되지 않았습니다.\n리그 설정에서 세이브를 선택하세요.",
            )
            return

        self.import_button.setEnabled(False)
        since_mtime = self.settings_manager.get_last_boxscore_import_at(
            self.settings, boxscore_dir
        )
        self._import_worker = ImportWorker(
            self.aggregator,
            self.settings_manager,
            self.milestones,
            self.settings,
            boxscore_dir,
            self.settings.current_season,
            since_mtime=since_mtime,
            parent=self,
        )
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_import_finished(self, payload: ImportFinishedPayload) -> None:
        self.import_button.setEnabled(True)
        self.refresh()

        result = payload.batch
        parts = [f"{result.imported}경기 추가됨"]
        if payload.milestones_recorded:
            parts.append(f"마일스톤 {payload.milestones_recorded}건 달성")
        if result.skipped_existing:
            parts.append(f"DB 기존 {result.skipped_existing}건 스킵")
        if result.skipped_mtime:
            parts.append(f"미수정 {result.skipped_mtime}건 스킵")
        if result.skipped:
            parts.append(f"중복 {result.skipped}건")
        message = " · ".join(parts)
        self.import_finished.emit(message)

        if result.errors:
            details = "\n".join(
                f"game {item.game_id}: {item.error}" for item in result.errors[:10]
            )
            QMessageBox.warning(
                self,
                "가져오기 완료 (일부 오류)",
                f"{message}\n\n오류:\n{details}",
            )
        elif result.imported == 0 and not payload.milestones:
            QMessageBox.information(self, "가져오기 완료", message or "새 경기 없음")
        else:
            box = QMessageBox(self)
            box.setWindowTitle("가져오기 완료")
            box.setText(message)
            if payload.milestones:
                detail_button = box.addButton("자세히 보기", QMessageBox.ButtonRole.ActionRole)
                box.addButton(QMessageBox.StandardButton.Ok)
                box.exec()
                if box.clickedButton() == detail_button:
                    MilestoneAchievedDialog(payload.milestones, self).exec()
            else:
                box.exec()

    def _on_import_error(self, message: str) -> None:
        self.import_button.setEnabled(True)
        QMessageBox.critical(self, "가져오기 실패", message)

    def refresh(self) -> None:
        scope = self.scope_combo.currentText()
        season = self.settings.current_season

        if scope == "시즌 타격":
            data = self.aggregator.get_season_batting_totals(season)
            columns = ["선수", "팀", "AB", "H", "HR", "RBI", "BB", "SO", "SB", "2B", "3B"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ab", 0),
                    row.get("h", 0),
                    row.get("hr", 0),
                    row.get("rbi", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    row.get("sb", 0),
                    row.get("doubles", 0),
                    row.get("triples", 0),
                ]
                for row in data
            ]
        elif scope == "통산 타격":
            data = self.aggregator.get_career_batting_totals()
            columns = ["선수", "팀", "AB", "H", "HR", "RBI", "BB", "SO", "SB", "2B", "3B"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ab", 0),
                    row.get("h", 0),
                    row.get("hr", 0),
                    row.get("rbi", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    row.get("sb", 0),
                    row.get("doubles", 0),
                    row.get("triples", 0),
                ]
                for row in data
            ]
        elif scope == "시즌 투구":
            data = self.aggregator.get_season_pitching_totals(season)
            columns = ["선수", "팀", "IP", "H", "ER", "BB", "SO", "W", "L", "SV", "ERA"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    outs_to_ip_str(int(row.get("ip_outs", 0))),
                    row.get("h", 0),
                    row.get("er", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    row.get("w", 0),
                    row.get("l", 0),
                    row.get("sv", 0),
                    row.get("era", 0),
                ]
                for row in data
            ]
        else:
            data = self.aggregator.get_career_pitching_totals()
            columns = ["선수", "팀", "IP", "H", "ER", "BB", "SO", "W", "L", "SV", "ERA"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    outs_to_ip_str(int(row.get("ip_outs", 0))),
                    row.get("h", 0),
                    row.get("er", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    row.get("w", 0),
                    row.get("l", 0),
                    row.get("sv", 0),
                    row.get("era", 0),
                ]
                for row in data
            ]

        self.table_panel.table.setColumnCount(len(columns))
        self.table_panel.table.setHorizontalHeaderLabels(columns)
        self.table_panel.table.populate(rows)
