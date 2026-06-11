"""Player statistics tab with tracked-team filter."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.db.meta import get_init_season_coverage
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import outs_to_ip_str
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.player_game_log_dialog import PlayerGameLogDialog
from gui.widgets.table_widgets import SortableTable
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


class StatsView(QWidget):
    import_finished = pyqtSignal(str)

    BATTING_COLUMNS = [
        "G", "AB", "H", "2B", "3B", "HR", "RBI", "R", "BB", "K", "SB", "AVG", "OBP", "SLG", "OPS"
    ]
    PITCHING_COLUMNS = [
        "G", "GS", "W", "L", "SV", "IP", "K", "BB", "HR", "ERA", "WHIP", "CG", "SHO"
    ]

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
        self._players: list[dict] = []
        self._career_mode = False

        self.banner = ErrorBanner(self)
        self.import_button = QPushButton("박스스코어 가져오기")
        self.import_button.clicked.connect(self.start_import)
        self.mlb_only_checkbox = QCheckBox("MLB만")
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.setToolTip(
            "메이저리그 박스스코어만 가져옵니다. KBO·WBC 등은 건너뜁니다."
        )
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        self.career_toggle = QPushButton("통산 기록 보기")
        self.career_toggle.setCheckable(True)
        self.career_toggle.toggled.connect(self._on_career_toggled)

        self.season_combo = QComboBox()
        self.season_combo.currentIndexChanged.connect(self._on_season_changed)

        self.player_search = QComboBox()
        self.player_search.setEditable(True)
        self.player_search.lineEdit().setPlaceholderText("선수 검색...")
        self.player_search.lineEdit().textChanged.connect(lambda _t: self.refresh_players())

        self.player_list = QListWidget()
        self.player_list.currentRowChanged.connect(self._on_list_selection)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)

        self.batting_table = SortableTable(["항목"] + self.BATTING_COLUMNS)
        self.pitching_table = SortableTable(["항목"] + self.PITCHING_COLUMNS)
        self.batting_table.cellDoubleClicked.connect(self._open_game_logs)
        self.pitching_table.cellDoubleClicked.connect(self._open_game_logs)

        top = QHBoxLayout()
        top.addWidget(QLabel("선수 기록"))
        top.addStretch()
        top.addWidget(self.career_toggle)

        controls = QHBoxLayout()
        controls.addWidget(self.import_button)
        controls.addWidget(self.mlb_only_checkbox)
        controls.addWidget(self.progress_label)
        controls.addWidget(self.progress_bar, stretch=1)
        controls.addWidget(QLabel("시즌:"))
        controls.addWidget(self.season_combo)
        controls.addWidget(QLabel("검색:"))
        controls.addWidget(self.player_search)

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.info_label)
        right_panel.addWidget(QLabel("타격"))
        right_panel.addWidget(self.batting_table)
        right_panel.addWidget(QLabel("투구"))
        right_panel.addWidget(self.pitching_table)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.player_list)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addLayout(top)
        layout.addLayout(controls)
        layout.addWidget(splitter)

        self._reload_seasons()
        self.refresh_players()

    def _on_career_toggled(self, checked: bool) -> None:
        self._career_mode = checked
        self.career_toggle.setText("시즌 기록 보기" if checked else "통산 기록 보기")
        self.season_combo.setEnabled(not checked)
        self._refresh_player_stats()

    def _on_season_changed(self) -> None:
        if self.season_combo.currentData() == "career":
            self.career_toggle.setChecked(True)
        else:
            self.career_toggle.setChecked(False)
        self._refresh_player_stats()

    def _reload_seasons(self) -> None:
        self.season_combo.blockSignals(True)
        self.season_combo.clear()
        for season in self.aggregator.get_available_seasons():
            self.season_combo.addItem(str(season), season)
        if self.settings.current_season not in self.aggregator.get_available_seasons():
            self.season_combo.insertItem(0, str(self.settings.current_season), self.settings.current_season)
        index = self.season_combo.findData(self.settings.current_season)
        if index >= 0:
            self.season_combo.setCurrentIndex(index)
        self.season_combo.addItem("통산", "career")
        self.season_combo.blockSignals(False)

    def refresh_players(self) -> None:
        self._players = self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        self.player_list.clear()
        if not self._players:
            self.banner.show_info(
                "표시할 선수가 없습니다. 박스스코어를 가져오거나 tracked_teams 설정을 확인하세요."
            )
            return
        self.banner.hide()
        needle = self.player_search.currentText().strip().lower()
        for player in self._players:
            name = str(player.get("full_name") or player.get("short_name") or "")
            if needle and needle not in name.lower():
                continue
            icons = []
            if player.get("is_batter"):
                icons.append("B")
            if player.get("is_pitcher"):
                icons.append("P")
            prefix = "/".join(icons)
            item = QListWidgetItem(f"[{prefix}] {name}" if prefix else name)
            item.setData(Qt.ItemDataRole.UserRole, int(player["player_id"]))
            self.player_list.addItem(item)
        if self.player_list.count() and self.player_list.currentRow() < 0:
            self.player_list.setCurrentRow(0)

    def _on_list_selection(self, row: int) -> None:
        if row >= 0:
            self._refresh_player_stats()

    def _selected_player_id(self) -> int | None:
        item = self.player_list.currentItem()
        if not item:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_player_stats(self) -> None:
        player_id = self._selected_player_id()
        if player_id is None:
            self.info_label.setText("선수를 선택하세요.")
            self.batting_table.setRowCount(0)
            self.pitching_table.setRowCount(0)
            return

        career_mode = self._career_mode or self.season_combo.currentData() == "career"
        if career_mode:
            coverage = get_init_season_coverage(self.aggregator.conn)
            has_init = self.aggregator.player_has_init_stats(player_id)
            if has_init:
                self.info_label.setText(
                    f"통산 기록 (init {coverage}시즌까지 + 박스스코어)"
                )
            else:
                self.info_label.setText("초기값 없음 — 박스스코어 기록만 집계")
            self._fill_career_tables(player_id)
        else:
            season = int(self.season_combo.currentData())
            self.info_label.setText(f"{season}시즌 기록 (더블클릭: 경기별 기록)")
            self._fill_season_tables(player_id, season)

    def _fill_season_tables(self, player_id: int, season: int) -> None:
        batting = self.aggregator.get_batting_season(player_id, season)
        pitching = self.aggregator.get_pitching_season(player_id, season)
        self._set_stat_row(
            self.batting_table,
            batting,
            {
                "G": "games_played",
                "AB": "ab",
                "H": "h",
                "2B": "doubles",
                "3B": "triples",
                "HR": "hr",
                "RBI": "rbi",
                "R": "r",
                "BB": "bb",
                "K": "k",
                "SB": "sb",
                "AVG": "avg",
                "OBP": "obp",
                "SLG": "slg",
                "OPS": "ops",
            },
        )
        self._set_stat_row(
            self.pitching_table,
            pitching,
            {
                "G": "games",
                "GS": "games",
                "W": "wins",
                "L": "losses",
                "SV": "saves",
                "IP": "ip_display",
                "K": "k",
                "BB": "bb",
                "HR": "hr",
                "ERA": "era",
                "WHIP": "whip",
                "CG": "cg",
                "SHO": "sho",
            },
        )

    def _fill_career_tables(self, player_id: int) -> None:
        batting = self.aggregator.get_player_career_batting_row(player_id)
        pitching = self.aggregator.get_player_career_pitching_row(player_id)
        self._set_stat_row(
            self.batting_table,
            batting,
            {
                "G": "g",
                "AB": "ab",
                "H": "h",
                "2B": "doubles",
                "3B": "triples",
                "HR": "hr",
                "RBI": "rbi",
                "R": "r",
                "BB": "bb",
                "K": "k",
                "SB": "sb",
                "AVG": "avg",
            },
        )
        self._set_stat_row(
            self.pitching_table,
            pitching,
            {
                "G": "g",
                "GS": "gs",
                "W": "w",
                "L": "l",
                "SV": "s",
                "IP": "ip",
                "K": "k",
                "BB": "bb",
                "HR": "hr",
                "ERA": "era",
                "WHIP": "whip",
                "CG": "cg",
                "SHO": "sho",
            },
        )

    @staticmethod
    def _set_stat_row(table: SortableTable, data: dict | None, mapping: dict[str, str]) -> None:
        if not data:
            table.setRowCount(0)
            return
        row = ["기록"] + [data.get(mapping[col], "") for col in mapping]
        table.populate([row])

    def _open_game_logs(self, _row: int, _col: int) -> None:
        if self._career_mode:
            return
        player_id = self._selected_player_id()
        if player_id is None:
            return
        season_data = self.season_combo.currentData()
        if season_data == "career":
            return
        item = self.player_list.currentItem()
        if not item:
            return
        name = item.text().split("] ", 1)[-1]
        PlayerGameLogDialog(
            self.aggregator,
            self.settings,
            player_id,
            name,
            int(season_data),
            self,
        ).exec()

    def _on_mlb_only_toggled(self, checked: bool) -> None:
        self.settings.import_mlb_only = checked
        self.settings_manager.save(self.settings)

    def start_import(self) -> None:
        self.settings.import_mlb_only = self.mlb_only_checkbox.isChecked()
        boxscore_dir = self.settings.boxscore_dir
        if not boxscore_dir:
            self.banner.show_warning(
                "박스스코어 폴더가 설정되지 않았습니다. 하단 상태바를 클릭해 리그를 선택하세요."
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
        else:
            self.progress_label.setText(
                f"박스스코어 가져오는 중... ({current}/{total}) {filename}"
            )

    def _on_import_finished(self, payload: ImportFinishedPayload) -> None:
        self.import_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self._reload_seasons()
        self.refresh_players()
        self._refresh_player_stats()

        result = payload.batch
        parts = [f"{result.imported}경기 추가됨"]
        if result.skipped_non_mlb:
            parts.append(f"MLB 외 {result.skipped_non_mlb}건 스킵")
        if payload.milestones_recorded:
            parts.append(f"마일스톤 {payload.milestones_recorded}건 달성")
        message = " · ".join(parts)
        self.import_finished.emit(message)

        if result.errors:
            self.banner.show_warning(
                f"일부 오류: {len(result.errors)}건 — "
                f"{result.errors[0].error if result.errors else ''}"
            )
        elif result.imported == 0 and not payload.milestones:
            self.banner.show_info(message or "새 경기 없음")
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
