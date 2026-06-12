"""Bulk roster rating edit dialog."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.roster.age import age_from_row, get_reference_date
from core.roster.bulk_rating import (
    FameLevel,
    PlayerBulkSettings,
    apply_bulk_rules_to_row,
    should_modify_player,
)
from core.roster.combined import (
    CombinedRoster,
    load_combined_roster,
    resolve_combined_paths,
    save_modified_rosters,
    sync_player_rows_to_sources,
)
from core.roster.ootp_format import player_display_name
from core.roster.position_filter import POSITION_GROUP_OPTIONS, matches_position_group
from core.roster.row_access import row_get
from core.stats.aggregator import Aggregator

_FAME_OPTIONS: list[tuple[str, FameLevel]] = [
    ("미선택", FameLevel.NONE),
    ("지역구", FameLevel.REGIONAL),
    ("전국구", FameLevel.NATIONAL),
    ("슈퍼스타", FameLevel.SUPERSTAR),
]

_COL_EN = 0
_COL_KO = 1
_COL_AGE = 2
_COL_PROSPECT = 3
_COL_BASE = 4
_COL_PROSPECT_FAME = 5


class BulkRatingDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        import_export_dir: str,
        settings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.setWindowTitle("레이팅 일괄 편집")
        self.resize(1100, 700)

        mlb_path, kbo_path = resolve_combined_paths(import_export_dir)
        if not mlb_path and not kbo_path:
            raise FileNotFoundError("mlb_rosters / kbo_rosters 파일을 찾을 수 없습니다.")

        self.combined = load_combined_roster(mlb_path, kbo_path)
        if not self.combined.players:
            raise ValueError("로스터에 선수 데이터가 없습니다.")

        self.reference_date = get_reference_date(aggregator, settings)
        self._original_rows = {
            player.player_id: deepcopy(player.row) for player in self.combined.players
        }
        self._settings: dict[int, PlayerBulkSettings] = {}
        self._prospect_manual: set[int] = set()
        self._visible_ids: list[int] = []

        for player in self.combined.players:
            age = age_from_row(player.row, self.combined.fieldnames, self.reference_date)
            if age is None:
                age = 0
            self._settings[player.player_id] = PlayerBulkSettings(
                player_id=player.player_id,
                age=age,
                is_prospect=age <= 25,
            )

        self.prospect_boost = QCheckBox("유망주 레이팅 증가 적용")
        self.prospect_boost.setChecked(True)

        self.ref_label = QLabel(
            f"기준일: {self.reference_date.isoformat()} "
            f"(마지막 가져오기 날짜 우선)"
        )

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("이름 검색...")
        self.search_input.textChanged.connect(self._apply_filters)

        self.league_filter = QComboBox()
        self.league_filter.addItem("전체", "")
        self.league_filter.addItem("MLB", "mlb")
        self.league_filter.addItem("KBO", "kbo")
        self.league_filter.currentIndexChanged.connect(self._apply_filters)

        self.position_filter = QComboBox()
        for label, key in POSITION_GROUP_OPTIONS:
            self.position_filter.addItem(label, key)
        self.position_filter.currentIndexChanged.connect(self._apply_filters)

        self.prospect_only = QCheckBox("유망주만 보기")
        self.prospect_only.toggled.connect(self._apply_filters)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("검색:"))
        filter_row.addWidget(self.search_input, stretch=1)
        filter_row.addWidget(QLabel("리그:"))
        filter_row.addWidget(self.league_filter)
        filter_row.addWidget(QLabel("포지션:"))
        filter_row.addWidget(self.position_filter)
        filter_row.addWidget(self.prospect_only)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["영문명", "한글명", "나이", "유망주", "기본 인지도", "유망주 인지도"]
        )
        self.table.cellChanged.connect(self._on_cell_changed)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("적용 후 저장")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.prospect_boost)
        layout.addWidget(self.ref_label)
        layout.addLayout(filter_row)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)
        layout.addWidget(buttons)

        self._apply_filters()

    def _player_by_id(self) -> dict[int, object]:
        return {p.player_id: p for p in self.combined.players}

    def _apply_filters(self) -> None:
        needle = self.search_input.text().strip().lower()
        league = self.league_filter.currentData() or ""
        pos_group = self.position_filter.currentData()
        prospect_only = self.prospect_only.isChecked()
        fieldnames = self.combined.fieldnames

        visible: list[int] = []
        for player in self.combined.players:
            cfg = self._settings[player.player_id]
            if league and player.source != league:
                continue
            if prospect_only and not cfg.is_prospect:
                continue
            pos = row_get(player.row, fieldnames, "Position")
            if not matches_position_group(pos, pos_group):
                continue
            name = player_display_name(player.row, fieldnames).lower()
            if needle and needle not in name:
                continue
            visible.append(player.player_id)

        self._visible_ids = visible
        self._reload_table()

    def _reload_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._visible_ids))
        fieldnames = self.combined.fieldnames
        players = self._player_by_id()

        for row_idx, player_id in enumerate(self._visible_ids):
            player = players[player_id]
            cfg = self._settings[player_id]
            name = player_display_name(player.row, fieldnames)

            self.table.setItem(row_idx, _COL_EN, self._read_only_item(name, player_id))
            self.table.setItem(row_idx, _COL_KO, self._read_only_item("", player_id))

            age_item = QTableWidgetItem(str(cfg.age))
            age_item.setData(Qt.ItemDataRole.UserRole, player_id)
            age_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            self.table.setItem(row_idx, _COL_AGE, age_item)

            prospect_item = QTableWidgetItem()
            prospect_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            prospect_item.setData(Qt.ItemDataRole.UserRole, player_id)
            prospect_item.setCheckState(
                Qt.CheckState.Checked if cfg.is_prospect else Qt.CheckState.Unchecked
            )
            prospect_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            self.table.setItem(row_idx, _COL_PROSPECT, prospect_item)

            self.table.setCellWidget(
                row_idx, _COL_BASE, self._fame_combo(cfg.base_fame, player_id, "base")
            )
            self.table.setCellWidget(
                row_idx,
                _COL_PROSPECT_FAME,
                self._fame_combo(cfg.prospect_fame, player_id, "prospect"),
            )

        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

    @staticmethod
    def _read_only_item(text: str, player_id: int) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setData(Qt.ItemDataRole.UserRole, player_id)
        return item

    def _fame_combo(
        self, level: FameLevel, player_id: int, kind: str
    ) -> QComboBox:
        combo = QComboBox()
        for label, value in _FAME_OPTIONS:
            combo.addItem(label, value)
        index = combo.findData(level)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.setProperty("player_id", player_id)
        combo.setProperty("fame_kind", kind)
        combo.currentIndexChanged.connect(self._on_fame_changed)
        return combo

    def _on_fame_changed(self) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        player_id = combo.property("player_id")
        kind = combo.property("fame_kind")
        if player_id is None:
            return
        cfg = self._settings[int(player_id)]
        level = combo.currentData()
        if kind == "base":
            cfg.base_fame = level
        else:
            cfg.prospect_fame = level

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column == _COL_AGE:
            item = self.table.item(row, column)
            if item is None:
                return
            player_id = item.data(Qt.ItemDataRole.UserRole)
            if player_id is None:
                return
            player_id = int(player_id)
            try:
                age = int(item.text().strip())
            except ValueError:
                return
            cfg = self._settings[player_id]
            cfg.age = max(0, age)
            if player_id not in self._prospect_manual:
                cfg.is_prospect = cfg.age <= 25
                prospect_item = self.table.item(row, _COL_PROSPECT)
                if prospect_item:
                    self.table.blockSignals(True)
                    prospect_item.setCheckState(
                        Qt.CheckState.Checked
                        if cfg.is_prospect
                        else Qt.CheckState.Unchecked
                    )
                    self.table.blockSignals(False)
        elif column == _COL_PROSPECT:
            item = self.table.item(row, column)
            if item is None:
                return
            player_id = item.data(Qt.ItemDataRole.UserRole)
            if player_id is None:
                return
            player_id = int(player_id)
            self._prospect_manual.add(player_id)
            cfg = self._settings[player_id]
            cfg.is_prospect = item.checkState() == Qt.CheckState.Checked
            cfg.prospect_manual = True

    def _save(self) -> None:
        prospect_boost = self.prospect_boost.isChecked()
        fieldnames = self.combined.fieldnames
        players = self._player_by_id()
        to_modify = [
            pid
            for pid, cfg in self._settings.items()
            if should_modify_player(cfg, prospect_boost=prospect_boost)
        ]
        if not to_modify:
            QMessageBox.information(self, "변경 없음", "적용할 레이팅 변경이 없습니다.")
            return

        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setMaximum(len(to_modify))

        for index, player_id in enumerate(to_modify, start=1):
            cfg = self._settings[player_id]
            original = self._original_rows[player_id]
            players[player_id].row = apply_bulk_rules_to_row(
                original,
                fieldnames,
                cfg,
                prospect_boost=prospect_boost,
            )
            self.progress.setValue(index)
            self.progress_label.setText(f"적용 중... {index}/{len(to_modify)}")

        sync_player_rows_to_sources(self.combined)
        mlb_out, kbo_out = save_modified_rosters(self.combined)

        mlb_count = len(self.combined.mlb.rows) if self.combined.mlb else 0
        kbo_count = len(self.combined.kbo.rows) if self.combined.kbo else 0
        parts = []
        if mlb_out:
            parts.append(f"MLB {mlb_count:,}명 → {mlb_out.name}")
        if kbo_out:
            parts.append(f"KBO {kbo_count:,}명 → {kbo_out.name}")

        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        QMessageBox.information(
            self,
            "저장 완료",
            " · ".join(parts) if parts else "저장 완료",
        )
        self.accept()
