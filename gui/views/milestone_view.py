"""Milestone achievement history tab."""

from __future__ import annotations

import csv
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QTextEdit,
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
from core.parser.game_log_html import extract_player_at_bats
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams
from core.streak.export import export_streak_csvs as write_streak_csv_bundle
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.table_widgets import TablePanel
from gui.widgets.edit_milestone_record_dialog import EditMilestoneRecordDialog
from gui.widgets.manual_milestone_dialog import ManualMilestoneDialog
from gui.ui_compact import hint_style
from gui.theme import AMBER_300

_TABLE_COLUMNS = [
    "날짜",
    "선수 이름",
    "선수 이름(한글)",
    "소속팀",
    "내용",
    "경기수",
    "상대팀",
    "상대선수",
    "설명",
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
        self.scope_combo.addItem("연속기록", "streak")
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
        self.meta_label.setStyleSheet(f"padding: 6px; {hint_style()}")
        self.game_log_button = QPushButton("게임 로그 열기")
        self.game_log_button.setEnabled(False)
        self.game_log_button.clicked.connect(self._open_selected_game_log)

        self.log_hint_panel = QTextEdit()
        self.log_hint_panel.setReadOnly(True)
        self.log_hint_panel.setPlaceholderText("")
        self.log_hint_panel.setMaximumHeight(100)
        self.log_hint_panel.hide()

        self.refresh_button = QPushButton("새로고침")
        self.export_button = QPushButton("CSV로 보내기")
        self.export_streak_button = QPushButton("연속기록 내보내기")
        self.manual_button = QPushButton("수동 입력")
        self.season_ratio_button = QPushButton("시즌 비율 마일스톤 기록")
        self.edit_button = QPushButton("수정")
        self.delete_button = QPushButton("삭제")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export_history_csv)
        self.export_streak_button.clicked.connect(self.export_streak_csvs)
        self.manual_button.clicked.connect(self._open_manual_dialog)
        self.season_ratio_button.clicked.connect(self._record_season_ratio_milestones)
        self.edit_button.clicked.connect(self._edit_selected_record)
        self.delete_button.clicked.connect(self._delete_selected_record)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)
        self.table_panel.table.itemSelectionChanged.connect(self._update_meta_panel)
        self._edit_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.table_panel.table)
        self._edit_shortcut.activated.connect(self._edit_selected_record)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("대상:"))
        filter_row.addWidget(self.subject_combo)
        filter_row.addWidget(QLabel("팀:"))
        filter_row.addWidget(self.team_filter)
        filter_row.addWidget(QLabel("scope:"))
        filter_row.addWidget(self.scope_combo)
        filter_row.addWidget(QLabel("시즌:"))
        filter_row.addWidget(self.season_spin)
        filter_row.addStretch()

        action_row = QHBoxLayout()
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.export_button)
        action_row.addWidget(self.export_streak_button)
        action_row.addWidget(self.manual_button)
        action_row.addWidget(self.season_ratio_button)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch()
        action_row.addWidget(QLabel("F2: 수정 · 더블클릭: 게임 로그"))

        meta_row = QHBoxLayout()
        meta_row.addWidget(self.meta_label, stretch=1)
        meta_row.addWidget(self.game_log_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.addWidget(self.banner)
        layout.addLayout(filter_row)
        layout.addLayout(action_row)
        layout.addWidget(self.table_panel, stretch=1)
        layout.addWidget(self.log_hint_panel)
        layout.addLayout(meta_row)

        self._selected_record_id: int | None = None
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
            is_team = int(record.get("player_id") or 0) == 0 and bool(record.get("team"))
            display_name = str(record["team"]) if is_team else record["player_name"]
            affiliation = str(record.get("team") or "")
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
                affiliation,
                label,
                "" if games is None else str(games),
                record.get("opponent_team") or "",
                record.get("opponent_player") or "",
                record.get("description") or "",
                record.get("notes") or "",
            ]
            record_id = record.get("id")
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if record_id is not None:
                    item.setData(Qt.ItemDataRole.UserRole, int(record_id))
                if bool(record.get("is_manual")) and col_idx == 4:
                    item.setForeground(QColor(AMBER_300))
                if self._highlight_id is not None and record.get("id") == self._highlight_id:
                    item.setBackground(QColor("#422006"))
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
                is_team = int(record.get("player_id") or 0) == 0 and bool(record.get("team"))
                display_name = (
                    record["team"] if is_team else record.get("player_name", "")
                )
                affiliation = str(record.get("team") or "")
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
                        affiliation,
                        label,
                        "" if games is None else games,
                        record.get("opponent_team") or "",
                        record.get("opponent_player") or "",
                        record.get("description") or "",
                        record.get("notes") or "",
                    ]
                )
        self.banner.show_info(f"보내기 완료: {filepath}")

    def export_streak_csvs(self) -> None:
        season = self.season_spin.value() or self.settings.current_season
        default_root = (
            self.settings.import_export_dir or self.settings.initial_stats_dir or ""
        )
        default_dir = str(
            Path(default_root)
            / f"streak_export_{season}_{datetime.now():%Y%m%d}"
        )

        output_dir = QFileDialog.getExistingDirectory(
            self,
            f"연속기록 내보내기 ({season}시즌)",
            default_dir,
        )
        if not output_dir:
            return

        try:
            result = write_streak_csv_bundle(self.aggregator, output_dir, season)
        except OSError as exc:
            self.banner.show_error(f"연속기록 내보내기 실패: {exc}")
            return

        file_list = "\n".join(f"  · {path.name}" for path in result.files)
        self.banner.show_info(
            f"{season}시즌 연속기록 CSV {len(result.files)}개를 저장했습니다.\n{output_dir}\n{file_list}"
        )

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

    def _record_season_ratio_milestones(self) -> None:
        season = self.season_spin.value() or self.settings.current_season
        if season <= 0:
            QMessageBox.information(
                self,
                "시즌 선택",
                "시즌 필터에서 연도를 선택한 뒤 다시 시도하세요.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "시즌 비율 마일스톤 기록",
            f"{season}시즌 타율·출루율·장타율·OPS·ERA 마일스톤을 "
            "현재 DB 기준으로 기록합니다.\n\n"
            "시즌이 끝난 뒤 한 번 실행하는 것을 권장합니다. 계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        achievements = checker.check_season_ratios(season)
        recorded = checker.record_achievements(achievements)
        self.banner.show_info(
            f"{season}시즌 비율 마일스톤 {recorded}건 기록"
            + (f" (달성 후보 {len(achievements)}건)" if achievements else "")
        )
        self.refresh()
        self.records_changed.emit()

    def _selected_record_id_from_table(self) -> int | None:
        rows = self.table_panel.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table_panel.table.item(rows[0].row(), 0)
        if item is None:
            return None
        record_id = item.data(Qt.ItemDataRole.UserRole)
        return int(record_id) if record_id is not None else None

    def _selected_record(self) -> dict | None:
        record_id = self._selected_record_id_from_table()
        if record_id is None:
            return None
        return self.aggregator.get_milestone_record_by_id(record_id)

    def _edit_selected_record(self) -> None:
        record_id = self._selected_record_id_from_table()
        if record_id is None:
            QMessageBox.information(self, "수정", "수정할 기록을 선택하세요.")
            return
        try:
            dialog = EditMilestoneRecordDialog(
                self.aggregator,
                self.milestones,
                record_id,
                parent=self,
            )
        except ValueError:
            QMessageBox.warning(self, "수정", "선택한 기록을 찾을 수 없습니다.")
            self.refresh()
            return
        if dialog.exec():
            self._highlight_id = record_id
            self.refresh()
            self.records_changed.emit()

    def _delete_selected_record(self) -> None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "삭제", "삭제할 기록을 선택하세요.")
            return
        milestone = self.milestones.get_by_key(str(record["milestone_key"]))
        label = (
            milestone.label
            if milestone
            else record.get("milestone_label", record["milestone_key"])
        )
        is_team = int(record.get("player_id") or 0) == 0 and bool(record.get("team"))
        target = str(record["team"]) if is_team else str(record.get("player_name", ""))
        confirm = QMessageBox.question(
            self,
            "마일스톤 기록 삭제",
            f"다음 기록을 삭제하시겠습니까?\n\n{target} · {label}\n{record.get('achieved_date', '')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        record_id = int(record["id"])
        if not self.aggregator.delete_milestone_record(record_id):
            QMessageBox.warning(self, "삭제", "기록을 삭제하지 못했습니다.")
            return
        self.banner.show_info("마일스톤 기록을 삭제했습니다.")
        self.refresh()
        self.records_changed.emit()

    def _update_meta_panel(self) -> None:
        record = self._selected_record()
        if record is None:
            self._selected_record_id = None
            self.meta_label.setText("")
            self.game_log_button.setEnabled(False)
            self.log_hint_panel.hide()
            return
        self._selected_record_id = int(record["id"])
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
        self._update_log_hint_panel(record)

    def _update_log_hint_panel(self, record: dict) -> None:
        if record.get("description"):
            self.log_hint_panel.hide()
            return
        game_id = record.get("game_id")
        player_id = record.get("player_id")
        if not game_id or not player_id:
            self.log_hint_panel.hide()
            return
        logs_dir = self.settings.game_logs_dir
        if not logs_dir:
            self.log_hint_panel.setPlainText("게임 로그 경로가 설정되지 않았습니다.")
            self.log_hint_panel.show()
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            self.log_hint_panel.setPlainText("게임 로그 파일을 찾을 수 없습니다.")
            self.log_hint_panel.show()
            return
        try:
            entries = extract_player_at_bats(log_path, int(player_id))
        except Exception:
            self.log_hint_panel.setPlainText("게임 로그를 읽을 수 없습니다.")
            self.log_hint_panel.show()
            return
        if not entries:
            self.log_hint_panel.setPlainText("해당 선수의 타석 기록이 게임 로그에 없습니다.")
            self.log_hint_panel.show()
            return
        lines = [
            "게임 로그 참고 (자동 작성 아님 — 참고용)",
            "※ 위 내용을 참고해 「설명」을 직접 입력하세요.",
            "",
        ]
        for entry in entries:
            lines.append(f"[{entry['label']}] {entry['raw_text']}")
        self.log_hint_panel.setPlainText("\n".join(lines))
        self.log_hint_panel.show()

    def _open_selected_game_log(self) -> None:
        rows = self.table_panel.table.selectionModel().selectedRows()
        if not rows:
            return
        self._open_game_log(rows[0].row(), 0)

    def _open_game_log(self, row: int, _column: int) -> None:
        item = self.table_panel.table.item(row, 0)
        if item is None:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        if record_id is None:
            return
        record = self.aggregator.get_milestone_record_by_id(int(record_id))
        if not record:
            return
        game_id = record.get("game_id")
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
