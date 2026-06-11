"""Roster rating edit tab — per-player dialog on double-click."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
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
from core.roster.editor import RosterEditor, RosterFilter
from core.roster.ootp_format import player_age, player_display_name
from core.roster.paths import (
    RosterLeague,
    expected_roster_path,
    find_roster_file,
    roster_export_label,
)
from core.roster.position_filter import POSITION_GROUP_OPTIONS, position_label
from core.roster.row_access import row_get
from gui.widgets.player_rating_dialog import PlayerRatingDialog
from gui.widgets.table_widgets import TablePanel

_LEAGUE_ITEMS: list[tuple[str, RosterLeague]] = [
    ("MLB", "mlb"),
    ("KBO", "kbo"),
]

_TABLE_COLUMNS = ["이름", "팀", "리그", "포지션", "나이", "CON", "POW", "STU"]


class RosterView(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.editor = RosterEditor()
        self.editor.set_season_year(settings.current_season)
        self._filtered_rows: list[list[str]] = []
        self._loaded_path: Path | None = None
        self._current_league: RosterLeague = "mlb"

        self.league_combo = QComboBox()
        for label, league in _LEAGUE_ITEMS:
            self.league_combo.addItem(label, league)
        self.league_combo.currentIndexChanged.connect(self._on_league_changed)

        self.path_label = QLabel("파일: (없음)")
        self.reload_button = QPushButton("불러오기")
        self.reload_button.clicked.connect(lambda: self._reload_file(show_warning=True))

        self.position_combo = QComboBox()
        for label, group_key in POSITION_GROUP_OPTIONS:
            self.position_combo.addItem(label, group_key)

        self.min_age_input = QSpinBox()
        self.max_age_input = QSpinBox()
        for spin in (self.min_age_input, self.max_age_input):
            spin.setRange(0, 60)
            spin.setSpecialValueText("전체")
            spin.setValue(0)

        self.backup_button = QPushButton("원본 복사본 저장")
        self.save_button = QPushButton("저장")
        self.save_button.setEnabled(False)
        self.backup_button.clicked.connect(self.save_backup)
        self.save_button.clicked.connect(self.save_file)

        filter_button = QPushButton("필터 적용")
        filter_button.clicked.connect(self.apply_filter)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("리그"))
        source_row.addWidget(self.league_combo)
        source_row.addWidget(self.path_label, stretch=1)
        source_row.addWidget(self.reload_button)

        filter_form = QFormLayout()
        filter_form.addRow("포지션", self.position_combo)
        filter_form.addRow("최소 나이", self.min_age_input)
        filter_form.addRow("최대 나이", self.max_age_input)

        action_row = QHBoxLayout()
        action_row.addWidget(filter_button)
        action_row.addStretch()
        action_row.addWidget(self.backup_button)
        action_row.addWidget(self.save_button)

        self.table_panel = TablePanel(
            _TABLE_COLUMNS,
            placeholder="선수 검색...",
        )
        self.table_panel.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.info_label = QLabel(
            "세이브의 import_export 폴더에서 로스터를 불러옵니다. "
            "선수 더블클릭으로 레이팅을 편집하세요."
        )

        layout = QVBoxLayout(self)
        layout.addLayout(source_row)
        layout.addLayout(filter_form)
        layout.addLayout(action_row)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table_panel)

        self._reload_file(show_warning=False)

    def _import_export_dir(self) -> Path | None:
        directory = self.settings.import_export_dir or self.settings.initial_stats_dir
        if not directory:
            return None
        return Path(directory)

    def _on_league_changed(self) -> None:
        league = self.league_combo.currentData()
        if league:
            self._current_league = league
        self._reload_file(show_warning=True)

    def _resolve_roster_path(self) -> Path | None:
        export_dir = self._import_export_dir()
        return find_roster_file(export_dir, self._current_league)

    def _expected_path_display(self) -> str:
        export_dir = self._import_export_dir()
        if export_dir is None:
            return "(세이브 미설정)"
        return str(expected_roster_path(export_dir, self._current_league))

    def _optional_age(self, spin: QSpinBox) -> int | None:
        return spin.value() or None

    def _build_filter(self) -> RosterFilter:
        return RosterFilter(
            position_group=self.position_combo.currentData(),
            min_age=self._optional_age(self.min_age_input),
            max_age=self._optional_age(self.max_age_input),
            season_year=self.settings.current_season,
        )

    def _reload_file(self, *, show_warning: bool = True) -> None:
        export_dir = self._import_export_dir()
        if export_dir is None:
            self._loaded_path = None
            self.path_label.setText("파일: (세이브 미설정)")
            if show_warning:
                QMessageBox.warning(
                    self,
                    "파일 없음",
                    "활성 세이브가 설정되지 않았습니다.\n설정 탭에서 리그를 선택하세요.",
                )
            return

        path = self._resolve_roster_path()
        self.path_label.setText(
            f"파일: {path}" if path else f"파일: {self._expected_path_display()}"
        )
        if path is None:
            self._loaded_path = None
            if show_warning:
                label = roster_export_label(self._current_league)
                QMessageBox.warning(
                    self,
                    "파일 없음",
                    f"로스터 파일을 찾을 수 없습니다.\n\n"
                    f"경로: {expected_roster_path(export_dir, self._current_league)}\n"
                    f"({label} — import_export 폴더에 OOTP 로스터 export 필요)",
                )
            return

        try:
            self.editor.set_season_year(self.settings.current_season)
            self.editor.load(path)
        except Exception as exc:
            self._loaded_path = None
            QMessageBox.critical(self, "로드 실패", str(exc))
            return

        self._loaded_path = path
        self.save_button.setEnabled(False)
        self.info_label.setText(
            f"로드됨: {path.name} ({self.editor.row_count:,}명)"
        )
        self._filtered_rows = self.editor.filter_rows(self._build_filter())
        self._show_rows(self._filtered_rows)

    def apply_filter(self) -> None:
        if not self.editor.row_count:
            QMessageBox.warning(self, "데이터 없음", "먼저 로스터를 불러오세요.")
            return
        self._filtered_rows = self.editor.filter_rows(self._build_filter())
        self.info_label.setText(f"필터 결과: {len(self._filtered_rows):,}명")
        self._show_rows(self._filtered_rows)

    def _on_row_double_clicked(self, row_index: int, _column: int) -> None:
        item = self.table_panel.table.item(row_index, 0)
        if item is None:
            return
        data_index = item.data(Qt.ItemDataRole.UserRole)
        if data_index is None:
            return
        data_index = int(data_index)
        if data_index < 0 or data_index >= len(self._filtered_rows):
            return
        player_row = self._filtered_rows[data_index]
        dialog = PlayerRatingDialog(
            player_row,
            self.editor.fieldnames,
            season_year=self.settings.current_season,
            parent=self,
        )
        if dialog.exec():
            self._show_rows(self._filtered_rows)

    def save_backup(self) -> None:
        if not self._loaded_path:
            QMessageBox.warning(self, "파일 없음", "저장할 원본 파일이 없습니다.")
            return
        try:
            backup = self.editor.save_copy(self._loaded_path)
        except Exception as exc:
            QMessageBox.critical(self, "백업 실패", str(exc))
            return
        self.save_button.setEnabled(True)
        QMessageBox.information(self, "백업 완료", f"복사본 저장:\n{backup}")

    def save_file(self) -> None:
        if not self.editor.backup_saved:
            reply = QMessageBox.question(
                self,
                "백업 확인",
                "원본 복사본을 먼저 저장하지 않았습니다.\n지금 백업을 만든 뒤 저장할까요?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.save_backup()
        target = self._loaded_path
        if target is None:
            return
        try:
            saved = self.editor.save(target)
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        QMessageBox.information(self, "저장 완료", f"저장 위치: {saved}")

    def _show_rows(self, rows: list[list[str]]) -> None:
        fieldnames = self.editor.fieldnames
        season = self.settings.current_season
        display_rows = []
        for row in rows[:5000]:
            age = player_age(row, season_year=season, fieldnames=fieldnames)
            display_rows.append(
                [
                    player_display_name(row, fieldnames),
                    row_get(row, fieldnames, "Team Name"),
                    row_get(row, fieldnames, "League Name"),
                    position_label(row_get(row, fieldnames, "Position")),
                    "" if age is None else str(age),
                    row_get(row, fieldnames, "Contact vL"),
                    row_get(row, fieldnames, "Power vL"),
                    row_get(row, fieldnames, "Stuff Overall"),
                ]
            )
        table = self.table_panel.table
        table.setSortingEnabled(False)
        table.setRowCount(len(display_rows))
        for row_idx, values in enumerate(display_rows):
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem("" if value is None else str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row_idx)
                table.setItem(row_idx, col_idx, cell)
        if len(rows) > 5000:
            self.info_label.setText(
                f"{self.info_label.text()} (표시 상한 5,000명)"
            )
