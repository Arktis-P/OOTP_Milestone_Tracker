"""Milestone achievement history tab."""

from __future__ import annotations

import csv
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.i18n import tr
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
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.card_panel import CardPanel, section_label
from gui.theme import AMBER_TEXT, RED_TEXT, TEXT_SECONDARY, hint_style, meta_panel_style
from gui.widgets.grade_styles import GRADE_COLORS
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker

def _table_columns() -> list[str]:
    return [
        tr("Date"),
        tr("Player Name"),
        tr("Player Name (Korean)"),
        tr("Team"),
        tr("Milestone"),
        tr("Games"),
        tr("Opponent"),
        tr("Opp. Player"),
        tr("Description"),
        tr("Notes"),
    ]


class MilestoneView(QWidget):
    records_changed = pyqtSignal()
    import_finished = pyqtSignal(str)

    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        settings_manager: SettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.settings_manager = settings_manager or SettingsManager()
        self._import_worker: ImportWorker | None = None
        self._records: list[dict] = []
        self._highlight_id: int | None = None

        self.banner = ErrorBanner(self)

        self.import_button = QPushButton(tr("📥  Import Boxscores"))
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self.start_import)
        self.mlb_only_checkbox = QCheckBox(tr("MLB Only"))
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.setToolTip(tr("Imports Major League boxscores only. KBO, WBC, etc. are skipped."))
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.progress_label.setMaximumWidth(340)
        self.progress_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumWidth(120)
        self.progress_bar.setMaximumWidth(260)

        self.subject_combo = QComboBox()
        self.subject_combo.addItem(tr("All (subject)"), "all")
        self.subject_combo.addItem(tr("Personal Only"), "personal")
        self.subject_combo.addItem(tr("Team Only"), "team")
        self.subject_combo.currentIndexChanged.connect(self.refresh)

        self.team_filter = QComboBox()
        self.team_filter.addItem(tr("All Teams"), "")
        self._reload_team_filter()
        self.team_filter.currentIndexChanged.connect(self.refresh)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem(tr("All Scopes"), "")
        self.scope_combo.addItem(tr("Game"), "game")
        self.scope_combo.addItem(tr("Season"), "season")
        self.scope_combo.addItem(tr("Career"), "career")
        self.scope_combo.addItem(tr("Team Game"), "team_game")
        self.scope_combo.addItem(tr("Team Season"), "team_season")
        self.scope_combo.addItem(tr("Streak"), "streak")
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setSpecialValueText(tr("All"))
        self.season_spin.setMinimum(0)
        self.season_spin.setValue(0)
        self.season_spin.valueChanged.connect(self.refresh)

        self.table_panel = TablePanel(
            _table_columns(),
            placeholder=tr("Search player, team, or milestone..."),
        )
        self.table_panel.filter_bar.search_input.textChanged.connect(self.refresh)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(meta_panel_style())
        self.game_log_button = QPushButton(tr("🌐 Open Game Log"))
        self.game_log_button.setEnabled(False)
        self.game_log_button.clicked.connect(self._open_selected_game_log)

        self.log_hint_panel = QTextEdit()
        self.log_hint_panel.setReadOnly(True)
        self.log_hint_panel.setPlaceholderText("")
        self.log_hint_panel.setMaximumHeight(100)
        self.log_hint_panel.hide()

        self.refresh_button = QPushButton(tr("Refresh"))
        self.export_button = QPushButton(tr("Export to CSV"))
        self.export_streak_button = QPushButton(tr("Export Streak"))
        self.btn_manual_record = QPushButton(tr("Record"))
        self.btn_manual_award = QPushButton(tr("Award"))
        self.btn_manual_transfer = QPushButton(tr("Transfer"))
        self.btn_manual_injury = QPushButton(tr("Injury"))
        self.season_ratio_button = QPushButton(tr("Record Season Ratio Milestones"))
        self.edit_button = QPushButton(tr("Edit"))
        self.delete_button = QPushButton(tr("Delete"))
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export_history_csv)
        self.export_streak_button.clicked.connect(self.export_streak_csvs)
        self.btn_manual_record.clicked.connect(lambda: self._open_manual_dialog(0))
        self.btn_manual_award.clicked.connect(lambda: self._open_manual_dialog(1))
        self.btn_manual_transfer.clicked.connect(lambda: self._open_manual_dialog(2))
        self.btn_manual_injury.clicked.connect(lambda: self._open_manual_dialog(3))
        self.season_ratio_button.clicked.connect(self._record_season_ratio_milestones)
        self.edit_button.clicked.connect(self._edit_selected_record)
        self.delete_button.clicked.connect(self._delete_selected_record)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)
        self.table_panel.table.itemSelectionChanged.connect(self._update_meta_panel)
        self._edit_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.table_panel.table)
        self._edit_shortcut.activated.connect(self._edit_selected_record)
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table_panel.table)
        self._delete_shortcut.activated.connect(self._delete_selected_record)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(section_label(tr("Subject")))
        filter_row.addWidget(self.subject_combo)
        self.subject_combo.setMaximumWidth(88)
        filter_row.addWidget(section_label(tr("Team")))
        filter_row.addWidget(self.team_filter)
        self.team_filter.setMinimumWidth(100)
        self.team_filter.setMaximumWidth(150)
        filter_row.addWidget(section_label("SCOPE"))
        filter_row.addWidget(self.scope_combo)
        self.scope_combo.setMaximumWidth(120)
        filter_row.addWidget(section_label(tr("Season")))
        filter_row.addWidget(self.season_spin)
        self.season_spin.setMaximumWidth(72)
        filter_row.addWidget(section_label(tr("Search")))
        filter_row.addWidget(self.table_panel.filter_bar.search_input, stretch=1)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.mlb_only_checkbox)
        action_row.addWidget(self.progress_label)
        action_row.addWidget(self.progress_bar)
        action_row.addSpacing(20)
        action_row.addWidget(section_label(tr("Manual Entry")))
        action_row.addWidget(self.btn_manual_record)
        action_row.addWidget(self.btn_manual_award)
        action_row.addWidget(self.btn_manual_transfer)
        action_row.addWidget(self.btn_manual_injury)
        action_row.addSpacing(12)
        action_row.addWidget(self.season_ratio_button)
        action_row.addStretch()
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.export_button)
        action_row.addWidget(self.export_streak_button)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.delete_button)

        hint = QLabel(tr("F2: Edit · Del: Delete · Double-click: Game Log"))
        hint.setObjectName("mutedLabel")

        filter_card = CardPanel()
        filter_card.content_layout.addLayout(filter_row)
        filter_card.content_layout.addLayout(action_row)
        filter_card.content_layout.addWidget(hint)

        table_card = CardPanel(tr("Milestone History"))
        table_card.add_widget(self.table_panel.table)

        meta_row = QHBoxLayout()
        meta_row.addWidget(self.meta_label, stretch=1)
        meta_row.addWidget(self.game_log_button)
        self.meta_card = CardPanel()
        self.meta_card.content_layout.addLayout(meta_row)
        self.meta_card.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(filter_card)
        layout.addWidget(table_card, stretch=1)
        layout.addWidget(self.log_hint_panel)
        layout.addWidget(self.meta_card)

        self._selected_record_id: int | None = None
        self.refresh()

    def _reload_team_filter(self) -> None:
        current = self.team_filter.currentData()
        self.team_filter.blockSignals(True)
        self.team_filter.clear()
        self.team_filter.addItem(tr("All Teams"), "")
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
        self.refresh()

        if result.errors:
            self.banner.show_warning(
                tr("Some errors: {count} — ").format(count=len(result.errors))
                + (result.errors[0].error if result.errors else "")
            )
        elif result.imported == 0 and not payload.milestones:
            self.banner.show_info(message or tr("No new games"))
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
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_error(tr("Import failed: {message}").format(message=message))

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
            grade = milestone.grade if milestone else "common"
            is_injury = record.get("milestone_key") == "manual_injury"
            is_highlighted = (
                self._highlight_id is not None and record.get("id") == self._highlight_id
            )
            record_id = record.get("id")
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if record_id is not None:
                    item.setData(Qt.ItemDataRole.UserRole, int(record_id))

                if is_injury:
                    item.setForeground(QColor(RED_TEXT))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                else:
                    if grade in ("legendary", "epic", "rare"):
                        colors = GRADE_COLORS[grade]
                        if colors.get("bg"):
                            item.setBackground(QColor(colors["bg"]))
                        if colors.get("fg"):
                            item.setForeground(QColor(colors["fg"]))
                    if bool(record.get("is_manual")) and col_idx == 4:
                        item.setForeground(QColor(AMBER_TEXT))

                if is_highlighted:
                    item.setBackground(QColor("#3a2f00"))

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
            tr("Export Milestone History"),
            tr("Exports the full milestone history (regardless of current filter).\nDo you want to continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export Milestone History"),
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
            writer.writerow(_table_columns())
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
        self.banner.show_info(tr("Export complete: {filepath}").format(filepath=filepath))

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
            tr("Export Streak Records ({season} season)").format(season=season),
            default_dir,
        )
        if not output_dir:
            return

        try:
            result = write_streak_csv_bundle(self.aggregator, output_dir, season)
        except OSError as exc:
            self.banner.show_error(tr("Streak export failed: {error}").format(error=exc))
            return

        file_list = "\n".join(f"  · {path.name}" for path in result.files)
        self.banner.show_info(
            tr("{season} season — {count} streak CSV file(s) saved.\n{dir}\n{files}").format(
                season=season, count=len(result.files), dir=output_dir, files=file_list
            )
        )

    def _open_manual_dialog(self, tab: int = 0) -> None:
        dialog = ManualMilestoneDialog(
            self.aggregator,
            self.milestones,
            self.settings,
            initial_tab=tab,
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
                tr("Select Season"),
                tr("Please select a season year in the season filter and try again."),
            )
            return
        confirm = QMessageBox.question(
            self,
            tr("Record Season Ratio Milestones"),
            tr(
                "Records AVG/OBP/SLG/OPS/ERA milestones for {season} season based on current DB.\n\n"
                "Recommended to run once after the season ends. Continue?"
            ).format(season=season),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        default_date = f"{season}-12-31"
        date_str, ok = QInputDialog.getText(
            self,
            tr("Enter In-Game Date"),
            tr("Enter the in-game date for the season-end records (YYYY-MM-DD):"),
            text=default_date,
        )
        if not ok:
            return
        date_str = date_str.strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            QMessageBox.warning(
                self,
                tr("Invalid Date"),
                tr("Please enter the date in YYYY-MM-DD format."),
            )
            return
        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        achievements = checker.check_season_ratios(season, achieved_date=date_str)
        recorded = checker.record_achievements(achievements)
        self.banner.show_info(
            tr("{season} season — {count} ratio milestone(s) recorded").format(
                season=season, count=recorded
            )
            + (
                tr(" ({count} candidates)").format(count=len(achievements))
                if achievements
                else ""
            )
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

    def _selected_record_ids_from_table(self) -> list[int]:
        ids: list[int] = []
        for index in self.table_panel.table.selectionModel().selectedRows():
            item = self.table_panel.table.item(index.row(), 0)
            if item is not None:
                record_id = item.data(Qt.ItemDataRole.UserRole)
                if record_id is not None:
                    ids.append(int(record_id))
        return ids

    def _selected_record(self) -> dict | None:
        record_id = self._selected_record_id_from_table()
        if record_id is None:
            return None
        return self.aggregator.get_milestone_record_by_id(record_id)

    def _edit_selected_record(self) -> None:
        record_id = self._selected_record_id_from_table()
        if record_id is None:
            QMessageBox.information(self, tr("Edit"), tr("Please select a record to edit."))
            return
        try:
            dialog = EditMilestoneRecordDialog(
                self.aggregator,
                self.milestones,
                record_id,
                parent=self,
            )
        except ValueError:
            QMessageBox.warning(self, tr("Edit"), tr("The selected record could not be found."))
            self.refresh()
            return
        if dialog.exec():
            self._highlight_id = record_id
            self.refresh()
            self.records_changed.emit()

    def _delete_selected_record(self) -> None:
        record_ids = self._selected_record_ids_from_table()
        if not record_ids:
            QMessageBox.information(self, tr("Delete"), tr("Please select a record to delete."))
            return

        if len(record_ids) == 1:
            record = self.aggregator.get_milestone_record_by_id(record_ids[0])
            if record is None:
                QMessageBox.warning(self, tr("Delete"), tr("Failed to delete the record."))
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
                tr("Delete Milestone Record"),
                tr("Delete the following record?\n\n{target} · {label}\n{date}").format(
                    target=target, label=label, date=record.get("achieved_date", "")
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
        else:
            confirm = QMessageBox.question(
                self,
                tr("Delete Milestone Records"),
                tr("Delete {count} selected records?").format(count=len(record_ids)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        failed = sum(
            1 for rid in record_ids if not self.aggregator.delete_milestone_record(rid)
        )
        if failed:
            QMessageBox.warning(
                self,
                tr("Delete"),
                tr("Failed to delete {count} record(s).").format(count=failed),
            )
        else:
            count = len(record_ids)
            if count == 1:
                self.banner.show_info(tr("Milestone record deleted."))
            else:
                self.banner.show_info(
                    tr("{count} milestone records deleted.").format(count=count)
                )
        self.refresh()
        self.records_changed.emit()

    def _update_meta_panel(self) -> None:
        record = self._selected_record()
        if record is None:
            self._selected_record_id = None
            self.meta_label.setText("")
            self.game_log_button.setEnabled(False)
            self.log_hint_panel.hide()
            self.meta_card.setVisible(False)
            return
        self.meta_card.setVisible(True)
        self._selected_record_id = int(record["id"])
        parts: list[str] = []
        if record.get("scope"):
            parts.append(f"scope: {record['scope']}")
        if record.get("achieved_value") is not None:
            parts.append(tr("Value: {value}").format(value=record["achieved_value"]))
        if record.get("season"):
            parts.append(tr("Season: {season}").format(season=record["season"]))
        if record.get("game_id"):
            parts.append(tr("Game ID: {game_id}").format(game_id=record["game_id"]))
        if record.get("is_manual"):
            parts.append(tr("Manual entry"))
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
            self.log_hint_panel.setPlainText(tr("Game log directory is not configured."))
            self.log_hint_panel.show()
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            self.log_hint_panel.setPlainText(tr("Game log file not found."))
            self.log_hint_panel.show()
            return
        try:
            entries = extract_player_at_bats(log_path, int(player_id))
        except Exception:
            self.log_hint_panel.setPlainText(tr("Could not read game log."))
            self.log_hint_panel.show()
            return
        if not entries:
            self.log_hint_panel.setPlainText(tr("No at-bat records for this player in the game log."))
            self.log_hint_panel.show()
            return
        lines = [
            tr("Game Log Reference (not auto-filled — for reference only)"),
            tr("※ Use this as reference when entering the Description field manually."),
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
                tr("Game Log"),
                tr("No linked game for this manually entered record."),
            )
            return
        logs_dir = self.settings.game_logs_dir
        if not logs_dir:
            QMessageBox.information(self, tr("Game Log"), tr("Game log directory is not configured."))
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if not log_path.is_file():
            QMessageBox.information(
                self,
                tr("Game Log"),
                tr("File not found:\n{path}").format(path=log_path),
            )
            return
        webbrowser.open(log_path.resolve().as_uri())
