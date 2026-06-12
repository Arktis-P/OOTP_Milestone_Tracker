"""Milestone achievement history tab."""

from __future__ import annotations

import csv
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_player_full_names,
    load_roster_player_names,
)
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.table_widgets import TablePanel
from gui.widgets.manual_milestone_dialog import ManualMilestoneDialog

_TABLE_COLUMNS = [
    "날짜",
    "선수 이름",
    "선수 이름(한글)",
    "마일스톤 이름",
    "경기수",
    "상대팀",
    "상대선수",
    "마일스톤 설명",
    "비고",
]


class MilestoneView(QWidget):
    records_changed = pyqtSignal()

    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self._records: list[dict] = []
        self._highlight_id: int | None = None

        self.banner = ErrorBanner(self)

        self.subject_combo = QComboBox()
        self.subject_combo.addItem("전체", "all")
        self.subject_combo.addItem("개인만", "personal")
        self.subject_combo.addItem("팀만", "team")
        self.subject_combo.currentIndexChanged.connect(self.refresh)

        self.team_filter = QComboBox()
        self.team_filter.addItem("팀 전체", "")
        self._reload_team_filter()
        self.team_filter.currentIndexChanged.connect(self.refresh)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("전체 scope", "")
        self.scope_combo.addItem("경기", "game")
        self.scope_combo.addItem("시즌", "season")
        self.scope_combo.addItem("통산", "career")
        self.scope_combo.addItem("팀 경기", "team_game")
        self.scope_combo.addItem("팀 시즌", "team_season")
        self.scope_combo.addItem("팀 수동", "team_manual")
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setSpecialValueText("전체")
        self.season_spin.setMinimum(0)
        self.season_spin.setValue(0)
        self.season_spin.valueChanged.connect(self.refresh)

        self.table_panel = TablePanel(
            _TABLE_COLUMNS,
            placeholder="선수·팀 또는 마일스톤 검색...",
        )
        self.table_panel.filter_bar.search_input.textChanged.connect(self.refresh)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(
            "padding: 6px; color: #64748b; font-size: 12px;"
        )
        self.game_log_button = QPushButton("게임 로그 열기")
        self.game_log_button.setEnabled(False)
        self.game_log_button.clicked.connect(self._open_selected_game_log)

        self.refresh_button = QPushButton("새로고침")
        self.export_button = QPushButton("CSV로 보내기")
        self.manual_button = QPushButton("수동 입력")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export_history_csv)
        self.manual_button.clicked.connect(self._open_manual_dialog)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)
        self.table_panel.table.itemSelectionChanged.connect(self._update_meta_panel)

        button_row = QHBoxLayout()
        button_row.addWidget(QLabel("대상:"))
        button_row.addWidget(self.subject_combo)
        button_row.addWidget(QLabel("팀:"))
        button_row.addWidget(self.team_filter)
        button_row.addWidget(QLabel("scope:"))
        button_row.addWidget(self.scope_combo)
        button_row.addWidget(QLabel("시즌:"))
        button_row.addWidget(self.season_spin)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.manual_button)
        button_row.addStretch()
        button_row.addWidget(QLabel("더블클릭: 게임 로그 열기"))

        meta_row = QHBoxLayout()
        meta_row.addWidget(self.meta_label, stretch=1)
        meta_row.addWidget(self.game_log_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addLayout(button_row)
        layout.addWidget(self.table_panel)
        layout.addLayout(meta_row)

        self._selected_row: int | None = None
        self.refresh()

    def _reload_team_filter(self) -> None:
        current = self.team_filter.currentData()
        self.team_filter.blockSignals(True)
        self.team_filter.clear()
        self.team_filter.addItem("팀 전체", "")
        names = expand_tracked_teams(
            self.settings.tracked_teams, self.settings.custom_mlb_teams
        )
        for name in sorted(set(names)):
            self.team_filter.addItem(name, name)
        if current:
            index = self.team_filter.findData(current)
            if index >= 0:
                self.team_filter.setCurrentIndex(index)
        self.team_filter.blockSignals(False)

    def on_data_refreshed(self, kind: str) -> None:
        if kind in ("boxscore", "milestone", "all"):
            if kind == "all":
                self._reload_team_filter()
            self.refresh()

    def refresh(self) -> None:
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        scope = self.scope_combo.currentData()
        season = self.season_spin.value() or None
        search = self.table_panel.filter_bar.search_input.text().strip()
        subject = self.subject_combo.currentData() or "all"
        team = self.team_filter.currentData() or None
        self._records = checker.get_recorded_milestones(
            scope=scope or None,
            season=season,
            search=search,
            subject=subject,
            team=team or None,
        )
        mapper = load_korean_name_mapper()
        full_names = load_player_full_names(self.aggregator)
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir
        )

        self.table_panel.table.setSortingEnabled(False)
        self.table_panel.table.setRowCount(len(self._records))
        for row_idx, record in enumerate(self._records):
            milestone = self.milestones.get_by_key(record["milestone_key"])
            label = (
                milestone.label
                if milestone
                else record.get("milestone_label", record["milestone_key"])
            )
            is_team = bool(record.get("team"))
            display_name = str(record["team"]) if is_team else record["player_name"]
            korean_name = ""
            if not is_team:
                player_id = record.get("player_id")
                pid = int(player_id) if player_id else None
                korean_name = korean_display_for_player(
                    mapper,
                    full_name=full_names.get(pid) if pid else None,
                    player_id=pid,
                    roster_names=roster_names,
                )
            games = record.get("games_at_achievement")
            values = [
                record.get("achieved_date") or "",
                display_name,
                korean_name,
                label,
                "" if games is None else str(games),
                record.get("opponent_team") or "",
                record.get("opponent_player") or "",
                record.get("description") or "",
                record.get("notes") or "",
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bool(record.get("is_manual")) and col_idx == 3:
                    item.setForeground(QColor("#b45309"))
                if self._highlight_id is not None and record.get("id") == self._highlight_id:
                    item.setBackground(QColor("#FDE68A"))
                self.table_panel.table.setItem(row_idx, col_idx, item)
        self.table_panel.table.setSortingEnabled(True)
        if self._highlight_id is not None:
            for row_idx, record in enumerate(self._records):
                if record.get("id") == self._highlight_id:
                    self.table_panel.table.selectRow(row_idx)
                    break
            self._highlight_id = None

    def highlight_record(self, record_id: int | None) -> None:
        self._highlight_id = record_id
        self.refresh()

    def export_history_csv(self) -> None:
        confirm = QMessageBox.question(
            self,
            "마일스톤 이력보내기",
            "전체 마일스톤 이력을보냅니다 (현재 필터와 무관).\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "마일스톤 이력보내기",
            f"milestone_history_{datetime.now():%Y%m%d}.csv",
            "CSV Files (*.csv)",
        )
        if not filepath:
            return

        mapper = load_korean_name_mapper()
        full_names = load_player_full_names(self.aggregator)
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir
        )
        records = self.aggregator.get_all_milestone_records_export()
        with open(filepath, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(_TABLE_COLUMNS)
            for record in records:
                is_team = bool(record.get("team"))
                display_name = (
                    record["team"] if is_team else record.get("player_name", "")
                )
                korean_name = ""
                if not is_team:
                    pid = record.get("player_id")
                    player_id = int(pid) if pid else None
                    korean_name = korean_display_for_player(
                        mapper,
                        full_name=full_names.get(player_id) if player_id else None,
                        player_id=player_id,
                        roster_names=roster_names,
                    )
                milestone = self.milestones.get_by_key(record["milestone_key"])
                label = (
                    milestone.label
                    if milestone
                    else record.get("milestone_label", record["milestone_key"])
                )
                games = record.get("games_at_achievement")
                writer.writerow(
                    [
                        record.get("achieved_date") or "",
                        display_name,
                        korean_name,
                        label,
                        "" if games is None else games,
                        record.get("opponent_team") or "",
                        record.get("opponent_player") or "",
                        record.get("description") or "",
                        record.get("notes") or "",
                    ]
                )
        self.banner.show_info(f"보내기 완료: {filepath}")

    def _open_manual_dialog(self) -> None:
        dialog = ManualMilestoneDialog(
            self.aggregator,
            self.milestones,
            self.settings,
            parent=self,
        )
        if dialog.exec():
            self.refresh()
            self.records_changed.emit()

    def _update_meta_panel(self) -> None:
        rows = self.table_panel.table.selectionModel().selectedRows()
        if not rows:
            self._selected_row = None
            self.meta_label.setText("")
            self.game_log_button.setEnabled(False)
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._records):
            return
        self._selected_row = row
        record = self._records[row]
        parts: list[str] = []
        if record.get("scope"):
            parts.append(f"scope: {record['scope']}")
        if record.get("achieved_value") is not None:
            parts.append(f"달성 수치: {record['achieved_value']}")
        if record.get("season"):
            parts.append(f"시즌: {record['season']}")
        if record.get("game_id"):
            parts.append(f"경기 ID: {record['game_id']}")
        if record.get("is_manual"):
            parts.append("수동 입력")
        self.meta_label.setText(" · ".join(parts))
        self.game_log_button.setEnabled(bool(record.get("game_id")))

    def _open_selected_game_log(self) -> None:
        if self._selected_row is None:
            return
        self._open_game_log(self._selected_row, 0)

    def _open_game_log(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._records):
            return
        game_id = self._records[row].get("game_id")
        if not game_id:
            QMessageBox.information(
                self,
                "게임 로그",
                "수동 입력 기록에는 연결된 경기가 없습니다.",
            )
            return
        logs_dir = self.settings.game_logs_dir
        if not logs_dir:
            QMessageBox.information(self, "게임 로그", "게임 로그 경로가 설정되지 않았습니다.")
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            QMessageBox.information(
                self,
                "게임 로그",
                f"파일을 찾을 수 없습니다:\n{log_path}",
            )
            return
        webbrowser.open(log_path.resolve().as_uri())
