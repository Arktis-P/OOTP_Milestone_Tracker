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
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.i18n import tr
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.implementation import is_award_milestone
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
from gui.widgets.import_result import build_import_message, show_import_result_banner
from gui.widgets.table_widgets import TablePanel
from gui.widgets.edit_milestone_record_dialog import EditMilestoneRecordDialog
from gui.widgets.manual_milestone_dialog import ManualMilestoneDialog
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.card_panel import CardPanel, section_label
from gui.theme import AMBER_TEXT, RED_TEXT, TEXT_SECONDARY, hint_style, meta_panel_style
from gui.widgets.grade_styles import GRADE_COLORS
from gui.widgets.empty_state import EmptyStateWidget
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


EVENT_TYPE_OPTIONS = (
    ("official", "Official Milestone"),
    ("quasi", "Quasi Milestone"),
    ("personal", "Personal Best"),
    ("team", "Team Record"),
    ("streak", "Streak"),
    ("award", "Award"),
    ("transfer", "Transfer"),
    ("injury", "Injury"),
    ("other", "Other"),
)

EVENT_TYPE_LABELS = dict(EVENT_TYPE_OPTIONS)

# Fixed positions of the compact Type/Source columns in _table_columns().
TYPE_COLUMN_INDEX = 5
SOURCE_COLUMN_INDEX = 6


def event_type_display_label(event_type: str) -> str:
    """Human-readable label for a derived event type, matching the filter option text."""
    return tr(EVENT_TYPE_LABELS.get(event_type, "Other"))


def source_display_label(is_manual: bool) -> str:
    """Human-readable label for a record's automatic/manual source."""
    return tr("Manual") if is_manual else tr("Automatic")


def milestone_is_manual(record: dict) -> bool:
    """Determine whether a record counts as Manual source.

    Historical/current records with scope == 'team_manual' must be treated as
    Manual even if the legacy/current DB's is_manual flag is 0.
    """
    scope = str(record.get("scope") or "").lower()
    if scope == "team_manual":
        return True
    return bool(record.get("is_manual"))


def milestone_event_type(record: dict, definition=None) -> str:
    """Derive a timeline event type without overloading milestone grade.

    The key/scope checks also keep legacy and future quasi-milestone/personal-best
    rows useful even though today's database does not store a dedicated type.
    """
    key = str(record.get("milestone_key") or "").lower()
    scope = str(record.get("scope") or "").lower()
    category = str(getattr(definition, "category", "") or "").lower()
    stat = str(getattr(definition, "stat", "") or "").lower()
    template = str(getattr(definition, "description_template", "") or "").lower()
    metadata = " ".join((key, scope, category, stat, template))

    if key == "manual_injury" or "injury" in key:
        return "injury"
    if key.startswith("manual_transfer_") or "transfer" in key:
        return "transfer"
    is_team_subject = int(record.get("player_id") or 0) == 0 and bool(
        record.get("team")
    )
    if scope.startswith("team_") or is_team_subject:
        return "team"
    if (definition is not None and is_award_milestone(definition)) or "award" in metadata:
        return "award"
    if scope == "streak" or key.startswith("streak_"):
        return "streak"
    if any(
        token in metadata
        for token in ("personal_best", "career_best", "season_best", "game_best")
    ):
        return "personal"
    if any(token in metadata for token in ("near_milestone", "quasi_milestone", "quasi")):
        return "quasi"
    if scope in ("game", "season", "career", "season_ratio"):
        return "official"
    return "other"


def milestone_record_matches(
    record: dict,
    definition=None,
    *,
    event_type: str = "",
    grade: str = "",
    source: str = "",
) -> bool:
    """Apply the three timeline-only filters to a milestone record."""
    if event_type and milestone_event_type(record, definition) != event_type:
        return False
    record_grade = str(getattr(definition, "grade", "common") or "common")
    if grade and record_grade != grade:
        return False
    is_manual = milestone_is_manual(record)
    if source == "manual" and not is_manual:
        return False
    if source == "automatic" and is_manual:
        return False
    return True


def select_record_row(table, record_id: int) -> bool:
    """Select a record by table metadata, independent of the current sort order."""
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == record_id:
            table.selectRow(row)
            table.scrollToItem(item)
            return True
    return False

def _table_columns() -> list[str]:
    columns = [
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
    columns.insert(TYPE_COLUMN_INDEX, tr("Type"))
    columns.insert(SOURCE_COLUMN_INDEX, tr("Source"))
    return columns


class MilestoneView(QWidget):
    records_changed = pyqtSignal()
    import_finished = pyqtSignal(str)
    player_detail_requested = pyqtSignal(int)

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
        self.cancel_import_button = QPushButton(tr("Cancel"))
        self.cancel_import_button.clicked.connect(self._cancel_import)
        self.cancel_import_button.setVisible(False)
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

        self.event_type_combo = QComboBox()
        self.event_type_combo.addItem(tr("All Event Types"), "")
        for value, label in EVENT_TYPE_OPTIONS:
            self.event_type_combo.addItem(tr(label), value)
        self.event_type_combo.currentIndexChanged.connect(self.refresh)

        self.grade_combo = QComboBox()
        self.grade_combo.addItem(tr("All Grades"), "")
        for grade in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_combo.addItem(grade, grade)
        self.grade_combo.currentIndexChanged.connect(self.refresh)

        self.source_combo = QComboBox()
        self.source_combo.addItem(tr("All Sources"), "")
        self.source_combo.addItem(tr("Automatic"), "automatic")
        self.source_combo.addItem(tr("Manual"), "manual")
        self.source_combo.currentIndexChanged.connect(self.refresh)

        self.reset_filters_button = QPushButton(tr("Reset Filters"))
        self.reset_filters_button.setObjectName("linkButton")
        self.reset_filters_button.setToolTip(tr("No active filters."))
        self.reset_filters_button.clicked.connect(self.reset_filters)
        self.filter_summary_label = QLabel("")
        self.filter_summary_label.setObjectName("mutedLabel")
        self.filter_summary_label.setWordWrap(True)
        self.filter_summary_label.setToolTip(
            tr("Shows how many milestone records match the current filters.")
        )

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
        history_header = self.table_panel.table.horizontalHeader()
        for col_idx, width in ((TYPE_COLUMN_INDEX, 130), (SOURCE_COLUMN_INDEX, 90)):
            history_header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
            self.table_panel.table.setColumnWidth(col_idx, width)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(meta_panel_style())
        self.game_log_button = QPushButton(tr("🌐 Open Game Log"))
        self.game_log_button.setEnabled(False)
        self.game_log_button.clicked.connect(self._open_selected_game_log)
        self.player_detail_button = QPushButton(tr("View Player Details"))
        self.player_detail_button.setEnabled(False)
        self.player_detail_button.clicked.connect(self._open_selected_player)

        self.log_hint_panel = QTextEdit()
        self.log_hint_panel.setReadOnly(True)
        self.log_hint_panel.setPlaceholderText("")
        self.log_hint_panel.setMaximumHeight(100)
        self.log_hint_panel.hide()

        self.record_menu_button = QToolButton()
        self.record_menu_button.setText(tr("Add Record"))
        self.record_menu_button.setObjectName("primaryButton")
        self.record_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        record_menu = QMenu(self.record_menu_button)
        record_menu.addAction(tr("Milestone"), lambda: self._open_manual_dialog(0))
        record_menu.addAction(tr("Award"), lambda: self._open_manual_dialog(1))
        record_menu.addAction(tr("Team Move"), lambda: self._open_manual_dialog(2))
        record_menu.addAction(tr("Injury"), lambda: self._open_manual_dialog(3))
        self.record_menu_button.setMenu(record_menu)

        self.export_menu_button = QToolButton()
        self.export_menu_button.setText(tr("Export"))
        self.export_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(self.export_menu_button)
        export_menu.addAction(tr("Full History CSV"), self.export_history_csv)
        export_menu.addAction(tr("Streak CSV"), self.export_streak_csvs)
        self.export_menu_button.setMenu(export_menu)

        self.more_menu_button = QToolButton()
        self.more_menu_button.setText(tr("More"))
        self.more_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self.more_menu_button)
        more_menu.addAction(
            tr("Determine Final Season Records"), self._record_season_ratio_milestones
        )
        more_menu.addAction(tr("Refresh"), self.refresh)
        self.more_menu_button.setMenu(more_menu)

        self.edit_button = QPushButton(tr("Edit"))
        self.delete_button = QPushButton(tr("Delete"))
        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.edit_button.clicked.connect(self._edit_selected_record)
        self.delete_button.clicked.connect(self._delete_selected_record)
        self.table_panel.table.cellDoubleClicked.connect(self._open_game_log)
        self.table_panel.table.itemSelectionChanged.connect(self._update_meta_panel)
        self.table_panel.table.itemSelectionChanged.connect(self._update_selection_actions)
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

        type_filter_row = QHBoxLayout()
        type_filter_row.setSpacing(10)
        type_filter_row.addWidget(section_label(tr("Event Type")))
        type_filter_row.addWidget(self.event_type_combo)
        type_filter_row.addWidget(section_label(tr("Grade")))
        type_filter_row.addWidget(self.grade_combo)
        type_filter_row.addWidget(section_label(tr("Source")))
        type_filter_row.addWidget(self.source_combo)
        type_filter_row.addWidget(self.filter_summary_label, stretch=1)
        type_filter_row.addWidget(self.reset_filters_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.cancel_import_button)
        action_row.addWidget(self.mlb_only_checkbox)
        action_row.addWidget(self.progress_label)
        action_row.addWidget(self.progress_bar)
        action_row.addSpacing(20)
        action_row.addWidget(self.record_menu_button)
        action_row.addStretch()
        action_row.addWidget(self.export_menu_button)
        action_row.addWidget(self.more_menu_button)
        action_row.addSpacing(12)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.delete_button)

        hint = QLabel(tr("F2: Edit · Del: Delete · Double-click: Game Log"))
        hint.setObjectName("mutedLabel")

        filter_card = CardPanel()
        filter_card.content_layout.addLayout(filter_row)
        filter_card.content_layout.addLayout(type_filter_row)
        filter_card.content_layout.addLayout(action_row)
        filter_card.content_layout.addWidget(hint)

        table_card = CardPanel(tr("Milestone History"))
        table_card.add_widget(self.table_panel.table)
        self.empty_state = EmptyStateWidget()
        self.empty_state.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.empty_state.hide()
        table_card.add_widget(self.empty_state)

        meta_row = QHBoxLayout()
        meta_row.addWidget(self.meta_label, stretch=1)
        meta_row.addWidget(self.player_detail_button)
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
        self.cancel_import_button.setVisible(True)
        self.cancel_import_button.setEnabled(True)
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
        self._import_worker.completed.connect(self._on_import_finished)
        self._import_worker.cancelled.connect(self._on_import_cancelled)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.finished.connect(
            lambda worker=self._import_worker: self._finish_import_worker(worker)
        )
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
        self.cancel_import_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        self.import_finished.emit(build_import_message(payload))
        self.refresh()

        show_import_result_banner(
            self.banner,
            payload,
            on_view_milestones=lambda: MilestoneAchievedDialog(payload.milestones, self).exec(),
            on_view_error=lambda: QMessageBox.warning(
                self,
                tr("Import Errors"),
                payload.batch.errors[0].error if payload.batch.errors else "",
            ),
        )

    def _on_import_error(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.cancel_import_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_error(tr("Import failed: {message}").format(message=message))

    def _on_import_cancelled(self, message: str) -> None:
        self.import_button.setEnabled(True)
        self.cancel_import_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.banner.show_info(message)

    def _cancel_import(self) -> None:
        if self._import_worker and self._import_worker.isRunning():
            self.cancel_import_button.setEnabled(False)
            self.progress_label.setText(tr("Cancelling import after the current item..."))
            self._import_worker.cancel()

    def _finish_import_worker(self, worker: ImportWorker) -> None:
        if self._import_worker is worker:
            self._import_worker = None
        worker.deleteLater()

    def refresh(self) -> None:
        previous_record_id = self._highlight_id or self._selected_record_id_from_table()
        if previous_record_id is None:
            previous_record_id = self._selected_record_id
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
        records = checker.get_recorded_milestones(
            scope=scope or None,
            season=season,
            search=search,
            subject=subject,
            team=team or None,
        )
        event_type = str(self.event_type_combo.currentData() or "")
        grade_filter = str(self.grade_combo.currentData() or "")
        source_filter = str(self.source_combo.currentData() or "")
        self._records = []
        for record in records:
            definition = self.milestones.get_by_key(str(record.get("milestone_key") or ""))
            if not milestone_record_matches(
                record,
                definition,
                event_type=event_type,
                grade=grade_filter,
                source=source_filter,
            ):
                continue
            self._records.append(record)

        total_count = len(checker.get_recorded_milestones())
        self._update_filter_summary(len(self._records), total_count)
        self.table_panel.table.setVisible(bool(self._records))
        self.empty_state.setVisible(not self._records)
        if not self._records:
            if total_count == 0:
                self.empty_state.set_content(
                    "⚾", tr("No milestone records yet"),
                    tr("Import boxscores or add a manual record to build the history."),
                )
            else:
                self.empty_state.set_content(
                    "⌕", tr("No records match these filters"),
                    tr("Try a broader event type, grade, source, season, or search."),
                    [(tr("Reset Filters"), self.reset_filters)],
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
            event_type = milestone_event_type(record, milestone)
            type_label = event_type_display_label(event_type)
            is_manual = milestone_is_manual(record)
            source_label = source_display_label(is_manual)
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
            values.insert(TYPE_COLUMN_INDEX, type_label)
            values.insert(SOURCE_COLUMN_INDEX, source_label)
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
                if col_idx == TYPE_COLUMN_INDEX:
                    item.setToolTip(type_label)
                elif col_idx == SOURCE_COLUMN_INDEX:
                    item.setToolTip(source_label)

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
                    if is_manual and col_idx in (4, SOURCE_COLUMN_INDEX):
                        item.setForeground(QColor(AMBER_TEXT))

                if is_highlighted:
                    item.setBackground(QColor("#3a2f00"))

                self.table_panel.table.setItem(row_idx, col_idx, item)
        self.table_panel.table.setSortingEnabled(True)
        selected = False
        if previous_record_id is not None:
            selected = select_record_row(self.table_panel.table, previous_record_id)
        if self._highlight_id is not None:
            self._highlight_id = None
        if selected:
            self._update_meta_panel()
        else:
            self.table_panel.table.clearSelection()
            self._update_meta_panel()
        self._update_selection_actions()

    def _active_filter_descriptions(self) -> list[str]:
        """Return human-readable active filters for the history toolbar."""
        filters: list[str] = []
        for label, combo in (
            (tr("Subject"), self.subject_combo),
            (tr("Team"), self.team_filter),
            (tr("Scope"), self.scope_combo),
            (tr("Event Type"), self.event_type_combo),
            (tr("Grade"), self.grade_combo),
            (tr("Source"), self.source_combo),
        ):
            data = combo.currentData()
            if data not in (None, "", "all"):
                filters.append(f"{label}: {combo.currentText()}")
        season = self.season_spin.value()
        if season:
            filters.append(tr("Season: {season}").format(season=season))
        search = self.table_panel.filter_bar.search_input.text().strip()
        if search:
            filters.append(tr("Search: {text}").format(text=search))
        return filters

    def _update_filter_summary(self, shown: int, total: int) -> None:
        filters = self._active_filter_descriptions()
        count_text = tr("Showing {shown:,} / {total:,} records").format(
            shown=shown,
            total=total,
        )
        if filters:
            summary = count_text + tr(" · Active filters: {filters}").format(
                filters=", ".join(filters)
            )
            self.reset_filters_button.setEnabled(True)
            self.reset_filters_button.setToolTip(
                tr("Clear active filters: {filters}").format(filters=", ".join(filters))
            )
        else:
            summary = count_text + tr(" · No active filters")
            self.reset_filters_button.setEnabled(False)
            self.reset_filters_button.setToolTip(tr("No active filters."))
        self.filter_summary_label.setText(summary)
        self.filter_summary_label.setToolTip(summary)

    def reset_filters(self) -> None:
        """Clear every history filter in one action."""
        combos = (
            self.subject_combo, self.team_filter, self.scope_combo,
            self.event_type_combo, self.grade_combo, self.source_combo,
        )
        for combo in combos:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.season_spin.blockSignals(True)
        self.season_spin.setValue(0)
        self.season_spin.blockSignals(False)
        self.table_panel.filter_bar.search_input.blockSignals(True)
        self.table_panel.filter_bar.search_input.clear()
        self.table_panel.filter_bar.search_input.blockSignals(False)
        self.refresh()

    def highlight_record(self, record_id: int | None) -> None:
        self._highlight_id = record_id
        self.refresh()

    def focus_scope(self, scope: str) -> bool:
        """Select a history scope when navigating from another view."""
        index = self.scope_combo.findData(scope)
        if index < 0:
            return False
        self.scope_combo.setCurrentIndex(index)
        return True

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
                type_label = event_type_display_label(
                    milestone_event_type(record, milestone)
                )
                source_label = source_display_label(milestone_is_manual(record))
                row = [
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
                row.insert(TYPE_COLUMN_INDEX, type_label)
                row.insert(SOURCE_COLUMN_INDEX, source_label)
                writer.writerow(row)
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
            tr("Determine Final Season Records"),
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

    def _update_selection_actions(self) -> None:
        has_selection = bool(self.table_panel.table.selectionModel().selectedRows())
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def _record_has_player(self, record: dict | None) -> bool:
        player_id = int((record or {}).get("player_id") or 0)
        if player_id <= 0:
            return False
        row = self.aggregator.conn.execute(
            "SELECT 1 FROM players WHERE player_id = ?", (player_id,)
        ).fetchone()
        return row is not None

    def _open_selected_player(self) -> None:
        record = self._selected_record()
        if not self._record_has_player(record):
            return
        self.player_detail_requested.emit(int(record["player_id"]))

    def _update_meta_panel(self) -> None:
        record = self._selected_record()
        if record is None:
            self._selected_record_id = None
            self.meta_label.setText("")
            self.game_log_button.setEnabled(False)
            self.player_detail_button.setEnabled(False)
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
        self.player_detail_button.setEnabled(self._record_has_player(record))
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
