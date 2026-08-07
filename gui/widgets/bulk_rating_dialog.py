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
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.roster.age import age_from_row, get_reference_date
from core.roster.bulk_rating import (
    BulkRatingPlan,
    PlayerBulkSettings,
    apply_bulk_rating_plan,
    build_bulk_rating_plan,
    should_modify_player,
)
from core.roster.combined import (
    load_combined_roster,
    resolve_combined_paths,
    save_modified_rosters_safely,
    sync_player_rows_to_sources,
)
from core.roster.korean_names import KoreanNameMapper, load_korean_name_mapper
from core.roster.ootp_format import player_display_name
from core.roster.position_filter import POSITION_GROUP_OPTIONS, matches_position_group
from core.stats.aggregator import Aggregator
from gui.utils.file_open import open_path_in_default_app
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import (
    add_dialog_footer,
    init_dialog_layout,
    make_button_box,
    muted_label,
    style_primary_button,
    summary_label,
    table_card,
    toolbar_row,
)
from gui.widgets.card_panel import CardPanel, section_label
from gui.widgets.bulk_rating_table import (
    COL_BASE,
    COL_EN,
    COL_KO,
    COL_PROSPECT_FAME,
    COL_TEAM,
    BulkPlayerIndex,
    BulkRatingTableModel,
    FameRadioDelegate,
)


PREVIEW_ROW_LIMIT = 500


def _field_label(header: str, occurrence: int) -> str:
    occurrence_label = f" #{occurrence + 1}" if occurrence else ""
    return f"{header}{occurrence_label}"


class BulkRatingPreviewDialog(QDialog):
    """Before-save preview that keeps destructive bulk edits reviewable."""

    def __init__(
        self,
        plan: BulkRatingPlan,
        player_names: dict[int, str],
        parent: QWidget | None = None,
        *,
        row_limit: int = PREVIEW_ROW_LIMIT,
    ) -> None:
        super().__init__(parent)
        self.plan = plan
        self.player_names = player_names
        self.row_limit = row_limit
        self.setWindowTitle(tr("Confirm Rating Changes"))
        self.resize(*scale_size(1200, 900))

        summary = summary_label(
            tr(
                "Changed {players:,} players / {cells:,} cells · "
                "Unchanged {unchanged:,} · Skipped {skipped:,} · "
                "Invalid cells {skipped_cells:,}"
            ).format(
                players=plan.changed_player_count,
                cells=plan.changed_cell_count,
                unchanged=len(plan.unchanged),
                skipped=len(plan.skipped),
                skipped_cells=plan.skipped_cell_count,
            )
        )
        summary.setWordWrap(True)

        self.change_table = QTableWidget(0, 4)
        self.change_table.setHorizontalHeaderLabels(
            [tr("Player"), tr("Field"), tr("Before"), tr("After")]
        )
        self.change_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.change_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.change_table.setAlternatingRowColors(True)
        header = self.change_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._populate_change_table()

        shown_cells = self.change_table.rowCount()
        if plan.changed_cell_count > shown_cells:
            limit_note_text = tr(
                "Showing the first {shown:,} changed cells. {remaining:,} more changed cells will also be applied."
            ).format(
                shown=shown_cells,
                remaining=plan.changed_cell_count - shown_cells,
            )
        else:
            limit_note_text = tr("All changed cells are shown.")
        limit_note = muted_label(limit_note_text)

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(100)
        self.detail_text.setMaximumHeight(160)
        self.detail_text.setPlainText(self._detail_text())

        self.buttons = make_button_box(save=True, save_text="Apply and Save")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        cancel = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setDefault(True)
            cancel.setAutoDefault(True)
        apply_button = next(
            button
            for button in self.buttons.buttons()
            if self.buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole
        )
        apply_button.setDefault(False)
        apply_button.setAutoDefault(False)

        layout = init_dialog_layout(self)
        layout.addWidget(summary)
        layout.addWidget(
            muted_label(tr("Review the exact before/after rating changes before saving."))
        )
        layout.addWidget(table_card(tr("Rating Changes"), self.change_table), stretch=1)
        layout.addWidget(limit_note)
        layout.addWidget(table_card(tr("Unchanged and Skipped Details"), self.detail_text))
        add_dialog_footer(layout, self.buttons)

    def _player_name(self, player_id: int) -> str:
        return str(self.player_names.get(player_id, player_id))

    def _populate_change_table(self) -> None:
        rows: list[tuple[str, str, str, str]] = []
        for player_change in self.plan.changes:
            name = self._player_name(player_change.player_id)
            for cell in player_change.cells:
                rows.append(
                    (name, _field_label(cell.header, cell.occurrence), cell.before, cell.after)
                )
                if len(rows) >= self.row_limit:
                    break
            if len(rows) >= self.row_limit:
                break

        self.change_table.setRowCount(len(rows))
        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.change_table.setItem(row_idx, col_idx, item)

    def _detail_text(self) -> str:
        sections: list[str] = []

        def add_player_reason_section(title: str, rows: tuple[tuple[int, str], ...]) -> None:
            sections.append(title)
            if rows:
                sections.extend(
                    f"- {self._player_name(player_id)} (ID {player_id}): {reason}"
                    for player_id, reason in rows
                )
            else:
                sections.append(tr("- None"))
            sections.append("")

        add_player_reason_section(tr("Unchanged targets"), self.plan.unchanged)
        add_player_reason_section(tr("Skipped players"), self.plan.skipped)
        sections.append(tr("Skipped cells"))
        if self.plan.skipped_cells:
            for cell in self.plan.skipped_cells:
                sections.append(
                    f"- {self._player_name(cell.player_id)} (ID {cell.player_id}) "
                    f"{_field_label(cell.header, cell.occurrence)}: {cell.reason}"
                )
        else:
            sections.append(tr("- None"))
        return "\n".join(sections).strip()


class BulkRatingSaveResultDialog(QDialog):
    """Post-save result with safe follow-up actions for outputs and backups."""

    def __init__(
        self,
        *,
        changed_players: int,
        changed_cells: int,
        output_paths,
        backup_paths,
        parent: QWidget | None = None,
        opener=open_path_in_default_app,
    ) -> None:
        super().__init__(parent)
        self._opener = opener
        self.output_paths = [path for path in output_paths if path is not None]
        self.backup_paths = [path for path in backup_paths if path is not None]
        self.setWindowTitle(tr("Rating Changes Saved"))
        self.resize(*scale_size(980, 620))

        summary = summary_label(
            tr("Changed {players:,} players / {cells:,} cells").format(
                players=changed_players,
                cells=changed_cells,
            )
        )
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("errorLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlainText(self._detail_text())

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setDefault(True)
        self.output_button = QPushButton(tr("Open Output Folder"))
        self.backup_button = QPushButton(tr("Open Backup Folder"))
        output_folder = self._first_existing_parent(self.output_paths)
        backup_folder = self._first_existing_parent(self.backup_paths)
        if output_folder is not None and backup_folder is not None and output_folder == backup_folder:
            self.output_button.setText(tr("Open Output and Backup Folder"))
            self.buttons.addButton(self.output_button, QDialogButtonBox.ButtonRole.ActionRole)
            self.output_button.clicked.connect(lambda: self._open_folder(output_folder))
        else:
            if output_folder is not None:
                self.buttons.addButton(self.output_button, QDialogButtonBox.ButtonRole.ActionRole)
                self.output_button.clicked.connect(lambda: self._open_folder(output_folder))
            if backup_folder is not None:
                self.buttons.addButton(self.backup_button, QDialogButtonBox.ButtonRole.ActionRole)
                self.backup_button.clicked.connect(lambda: self._open_folder(backup_folder))
        self.buttons.rejected.connect(self.reject)

        layout = init_dialog_layout(self)
        layout.addWidget(summary)
        layout.addWidget(muted_label(tr("Saved roster outputs and backups are listed below.")))
        layout.addWidget(table_card(tr("Save Result"), self.detail_text), stretch=1)
        layout.addWidget(self.warning_label)
        add_dialog_footer(layout, self.buttons)

    def _detail_text(self) -> str:
        lines = [tr("Output files")]
        if self.output_paths:
            lines.extend(f"- {path}" for path in self.output_paths)
        else:
            lines.append(tr("- None"))
        lines.extend(("", tr("Backup files")))
        if self.backup_paths:
            lines.extend(f"- {path}" for path in self.backup_paths)
            lines.extend(("", tr("Use these backups to restore the original roster files.")))
        else:
            lines.append(tr("- None"))
        return "\n".join(lines)

    @staticmethod
    def _first_existing_parent(paths):
        for path in paths:
            parent = path.parent
            if parent.exists():
                return parent
        return None

    def _open_folder(self, folder) -> None:
        if not self._opener(folder):
            self.warning_label.setText(
                tr("Could not open folder. Use the path shown above: {path}").format(
                    path=folder
                )
            )
            self.warning_label.show()


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
        self.setWindowTitle(tr("Bulk Rating Editor"))
        self.resize(*scale_size(2200, 1400))

        mlb_path, kbo_path = resolve_combined_paths(import_export_dir)
        if not mlb_path and not kbo_path:
            raise FileNotFoundError(
                tr("mlb_rosters / kbo_rosters files not found.")
            )

        self.combined = load_combined_roster(mlb_path, kbo_path)
        if not self.combined.players:
            raise ValueError(tr("No player data in roster."))

        self.reference_date = get_reference_date(aggregator, settings)
        self._settings: dict[int, PlayerBulkSettings] = {}
        self._player_indices: list[BulkPlayerIndex] = []
        self._korean_names = load_korean_name_mapper()

        for player in self.combined.players:
            fieldnames = player.fieldnames
            age = age_from_row(player.row, fieldnames, self.reference_date)
            if age is None:
                age = 0
            nation = player.value("Nation").strip()
            self._settings[player.player_id] = PlayerBulkSettings(
                player_id=player.player_id,
                age=age,
                is_prospect=age <= 25,
                nation=nation,
            )
            name = player_display_name(player.row, fieldnames)
            last_name = player.value("LastName").strip()
            first_name = player.value("FirstName").strip()
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
                    team=player.value("Team Name").strip(),
                    nation=nation,
                    position=player.value("Position"),
                    source=player.source,
                )
            )

        self.prospect_boost = QCheckBox(
            tr("Apply prospect rating boost (nation filter: applies to that nation only)")
        )
        self.prospect_boost.setChecked(False)

        self.ref_label = muted_label(
            tr("Reference date: {date} (last import date takes priority)").format(
                date=self.reference_date.isoformat()
            )
        )
        self.count_label = summary_label()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("Search by name..."))
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())

        self.league_filter = QComboBox()
        self.league_filter.addItem(tr("All"), "")
        self.league_filter.addItem("MLB", "mlb")
        self.league_filter.addItem("KBO", "kbo")
        self.league_filter.currentIndexChanged.connect(self._apply_filters)

        self.nation_filter = QComboBox()
        self.nation_filter.addItem(tr("All"), "")
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

        self.prospect_only = QCheckBox(tr("Prospects only"))
        self.prospect_only.toggled.connect(self._apply_filters)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(section_label(tr("Search")))
        filter_row.addWidget(self.search_input, stretch=1)
        filter_row.addWidget(section_label(tr("League")))
        filter_row.addWidget(self.league_filter)
        filter_row.addWidget(section_label(tr("Nation")))
        filter_row.addWidget(self.nation_filter)
        filter_row.addWidget(section_label(tr("Position")))
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

        buttons = make_button_box(save=True, save_text="Apply and Save")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self._save_button = next(
            button
            for button in buttons.buttons()
            if buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._save_button.setEnabled(False)
        self.prospect_boost.toggled.connect(self._update_save_state)
        self.model.dataChanged.connect(self._update_save_state)

        options_card = CardPanel(tr("Options"))
        options_card.add_widget(self.prospect_boost)
        options_card.add_widget(self.ref_label)

        filter_card = CardPanel(tr("Filter"))
        filter_card.add_layout(filter_row)

        table_panel = table_card(tr("Player List"), self.table)
        table_panel.content_layout.insertWidget(0, self.count_label)

        layout = init_dialog_layout(self)
        layout.addWidget(options_card)
        layout.addWidget(filter_card)
        layout.addWidget(table_panel, stretch=1)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)
        add_dialog_footer(layout, buttons)

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
        self.count_label.setText(
            tr("Apply scope: {shown:,} currently displayed / {total:,} total players").format(
                shown=shown, total=total
            )
        )
        self._update_save_state()

    def _update_save_state(self, *_args) -> None:
        if not hasattr(self, "_save_button"):
            return
        prospect_boost = self.prospect_boost.isChecked()
        prospect_nation = self.nation_filter.currentData() or None
        self._save_button.setEnabled(
            any(
                should_modify_player(
                    self._settings[player_id],
                    prospect_boost=prospect_boost,
                    prospect_nation=prospect_nation,
                )
                for player_id in self.model.visible_player_ids()
            )
        )

    def _preview_text(self, plan: BulkRatingPlan) -> str:
        names = {meta.player_id: meta.display_name for meta in self._player_indices}
        lines: list[str] = []
        for player_change in plan.changes:
            name = names.get(player_change.player_id, str(player_change.player_id))
            lines.append(f"{name} (ID {player_change.player_id})")
            for cell in player_change.cells:
                occurrence = f" #{cell.occurrence + 1}" if cell.occurrence else ""
                lines.append(f"  {cell.header}{occurrence}: {cell.before} -> {cell.after}")
        if plan.unchanged:
            lines.extend(("", tr("Unchanged targets:")))
            lines.extend(
                f"  {names.get(player_id, player_id)} (ID {player_id}): {reason}"
                for player_id, reason in plan.unchanged
            )
        if plan.skipped:
            lines.extend(("", tr("Skipped targets:")))
            lines.extend(
                f"  {names.get(player_id, player_id)} (ID {player_id}): {reason}"
                for player_id, reason in plan.skipped
            )
        if plan.skipped_cells:
            lines.extend(("", tr("Skipped cells:")))
            for cell in plan.skipped_cells:
                occurrence = f" #{cell.occurrence + 1}" if cell.occurrence else ""
                lines.append(
                    f"  {names.get(cell.player_id, cell.player_id)} (ID {cell.player_id}) "
                    f"{cell.header}{occurrence}: {cell.reason}"
                )
        return "\n".join(lines)

    def _confirm_plan(self, plan: BulkRatingPlan) -> bool:
        names = {meta.player_id: meta.display_name for meta in self._player_indices}
        dialog = BulkRatingPreviewDialog(plan, names, self)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _show_no_changes_plan(self, plan: BulkRatingPlan) -> None:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle(tr("No Changes"))
        message.setText(
            tr(
                "No rating cells would change in the current displayed scope. "
                "{skipped_players:,} players and {skipped_cells:,} invalid cells "
                "were skipped; see details for reasons."
            ).format(
                skipped_players=len(plan.skipped),
                skipped_cells=plan.skipped_cell_count,
            )
        )
        message.setDetailedText(self._preview_text(plan))
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.exec()

    def _save(self) -> None:
        self._search_timer.stop()
        self._apply_filters()
        prospect_boost = self.prospect_boost.isChecked()
        prospect_nation = self.nation_filter.currentData() or None
        plan = build_bulk_rating_plan(
            self.combined.players,
            self.model.visible_player_ids(),
            self._settings,
            prospect_boost=prospect_boost,
            prospect_nation=prospect_nation,
        )
        if not plan.changes:
            self._show_no_changes_plan(plan)
            return
        if not self._confirm_plan(plan):
            return

        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setMaximum(plan.changed_player_count)

        self.progress_label.setText(tr("Saving confirmed rating changes..."))
        original_player_rows = {
            player.player_id: deepcopy(player.row) for player in self.combined.players
        }
        original_mlb_rows = deepcopy(self.combined.mlb.rows) if self.combined.mlb else None
        original_kbo_rows = deepcopy(self.combined.kbo.rows) if self.combined.kbo else None
        try:
            apply_bulk_rating_plan(self.combined.players, plan)
            sync_player_rows_to_sources(self.combined)
            result = save_modified_rosters_safely(self.combined)
        except Exception as exc:
            for player in self.combined.players:
                player.row = original_player_rows[player.player_id]
            if self.combined.mlb is not None and original_mlb_rows is not None:
                self.combined.mlb.rows = original_mlb_rows
            if self.combined.kbo is not None and original_kbo_rows is not None:
                self.combined.kbo.rows = original_kbo_rows
            self.progress.setVisible(False)
            self.progress_label.setVisible(False)
            QMessageBox.critical(
                self,
                tr("Save Failed"),
                tr("No output changes were kept. {error}").format(error=str(exc)),
            )
            return

        self.progress.setValue(plan.changed_player_count)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        BulkRatingSaveResultDialog(
            changed_players=plan.changed_player_count,
            changed_cells=plan.changed_cell_count,
            output_paths=[path for path in (result.mlb_output, result.kbo_output) if path],
            backup_paths=list(result.backups),
            parent=self,
        ).exec()
        self.accept()
