"""Bulk roster rating edit dialog."""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.roster.age import age_from_row, get_reference_date
from core.roster.bulk_rating import (
    PlayerBulkSettings,
    apply_bulk_rules_to_row,
    should_modify_player,
)
from core.roster.combined import (
    load_combined_roster,
    resolve_combined_paths,
    save_modified_rosters,
    sync_player_rows_to_sources,
)
from core.roster.korean_names import KoreanNameMapper, load_korean_name_mapper
from core.roster.ootp_format import player_display_name
from core.roster.position_filter import POSITION_GROUP_OPTIONS, matches_position_group
from core.roster.row_access import row_get
from core.stats.aggregator import Aggregator
from gui.widgets.bulk_rating_table import (
    COL_BASE,
    COL_EN,
    COL_PROSPECT_FAME,
    COL_TEAM,
    BulkPlayerIndex,
    BulkRatingTableModel,
    FameRadioDelegate,
)


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
        self._original_rows: dict[int, list[str]] = {}
        self._settings: dict[int, PlayerBulkSettings] = {}
        self._player_indices: list[BulkPlayerIndex] = []
        self._players_by_id = {p.player_id: p for p in self.combined.players}
        fieldnames = self.combined.fieldnames
        self._korean_names = load_korean_name_mapper()

        for player in self.combined.players:
            age = age_from_row(player.row, fieldnames, self.reference_date)
            if age is None:
                age = 0
            nation = row_get(player.row, fieldnames, "Nation").strip()
            self._settings[player.player_id] = PlayerBulkSettings(
                player_id=player.player_id,
                age=age,
                is_prospect=age <= 25,
                nation=nation,
            )
            name = player_display_name(player.row, fieldnames)
            last_name = row_get(player.row, fieldnames, "LastName").strip()
            first_name = row_get(player.row, fieldnames, "FirstName").strip()
            korean_name = self._korean_names.format_player_name(
                last_name,
                first_name,
                western_order=KoreanNameMapper.uses_western_name_order(nation),
            )
            self._player_indices.append(
                BulkPlayerIndex(
                    player_id=player.player_id,
                    display_name=name,
                    name_lower=name.lower(),
                    korean_name=korean_name,
                    korean_name_lower=korean_name.casefold(),
                    team=row_get(player.row, fieldnames, "Team Name").strip(),
                    nation=nation,
                    position=row_get(player.row, fieldnames, "Position"),
                    source=player.source,
                )
            )

        self.prospect_boost = QCheckBox("유망주 레이팅 증가 적용 (국가 필터 선택 시 해당 국가만)")
        self.prospect_boost.setChecked(True)

        self.ref_label = QLabel(
            f"기준일: {self.reference_date.isoformat()} "
            f"(마지막 가져오기 날짜 우선)"
        )
        self.count_label = QLabel()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("이름 검색...")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())

        self.league_filter = QComboBox()
        self.league_filter.addItem("전체", "")
        self.league_filter.addItem("MLB", "mlb")
        self.league_filter.addItem("KBO", "kbo")
        self.league_filter.currentIndexChanged.connect(self._apply_filters)

        self.nation_filter = QComboBox()
        self.nation_filter.addItem("전체", "")
        for nation in self._collect_nations():
            self.nation_filter.addItem(nation, nation)
        kr_index = self.nation_filter.findData("South Korea")
        if kr_index >= 0:
            self.nation_filter.setCurrentIndex(kr_index)
        self.nation_filter.currentIndexChanged.connect(self._apply_filters)

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
        filter_row.addWidget(QLabel("국가:"))
        filter_row.addWidget(self.nation_filter)
        filter_row.addWidget(QLabel("포지션:"))
        filter_row.addWidget(self.position_filter)
        filter_row.addWidget(self.prospect_only)

        self.model = BulkRatingTableModel(self._player_indices, self._settings, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            COL_EN, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            COL_KO, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            COL_TEAM, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            COL_BASE, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            COL_PROSPECT_FAME, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.SelectedClicked
        )
        fame_delegate = FameRadioDelegate(self.table)
        self.table.setItemDelegateForColumn(COL_BASE, fame_delegate)
        self.table.setItemDelegateForColumn(COL_PROSPECT_FAME, fame_delegate)
        self.table.setMouseTracking(True)

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
        layout.addWidget(self.count_label)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)
        layout.addWidget(buttons)

        self._apply_filters()

    def _collect_nations(self) -> list[str]:
        nations = {meta.nation for meta in self._player_indices if meta.nation}
        return sorted(nations, key=str.casefold)

    def _apply_filters(self) -> None:
        needle = self.search_input.text().strip().lower()
        league = self.league_filter.currentData() or ""
        nation = self.nation_filter.currentData() or ""
        pos_group = self.position_filter.currentData()
        prospect_only = self.prospect_only.isChecked()

        visible_positions: list[int] = []
        for pos, meta in enumerate(self._player_indices):
            cfg = self._settings[meta.player_id]
            if league and meta.source != league:
                continue
            if nation and meta.nation != nation:
                continue
            if prospect_only and not cfg.is_prospect:
                continue
            if not matches_position_group(meta.position, pos_group):
                continue
            if needle and needle not in meta.name_lower and needle not in meta.korean_name_lower:
                continue
            visible_positions.append(pos)

        self.model.set_visible_rows(visible_positions)
        total = len(self._player_indices)
        shown = len(visible_positions)
        self.count_label.setText(f"표시 {shown:,}명 / 전체 {total:,}명")

    def _snapshot_original(self, player_id: int) -> list[str]:
        cached = self._original_rows.get(player_id)
        if cached is not None:
            return cached
        player = self._players_by_id[player_id]
        cached = deepcopy(player.row)
        self._original_rows[player_id] = cached
        return cached

    def _save(self) -> None:
        prospect_boost = self.prospect_boost.isChecked()
        prospect_nation = self.nation_filter.currentData() or None
        fieldnames = self.combined.fieldnames
        to_modify = [
            pid
            for pid, cfg in self._settings.items()
            if should_modify_player(
                cfg,
                prospect_boost=prospect_boost,
                prospect_nation=prospect_nation,
            )
        ]
        if not to_modify:
            QMessageBox.information(self, "변경 없음", "적용할 레이팅 변경이 없습니다.")
            return

        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setMaximum(len(to_modify))

        for index, player_id in enumerate(to_modify, start=1):
            cfg = self._settings[player_id]
            original = self._snapshot_original(player_id)
            self._players_by_id[player_id].row = apply_bulk_rules_to_row(
                original,
                fieldnames,
                cfg,
                prospect_boost=prospect_boost,
                prospect_nation=prospect_nation,
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
