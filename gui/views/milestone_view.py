"""Milestone achievement history tab."""

from __future__ import annotations

import csv
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
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
from core.stats.initial_import import (
    SNAPSHOT_BATTING_FILENAME,
    SNAPSHOT_PITCHING_FILENAME,
    ExportSnapshotError,
    InitialImporter,
)
from core.stats.team_filter import expand_tracked_teams
from core.streak.export import export_streak_csvs as write_streak_csv_bundle
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.import_errors_dialog import ImportErrorsDialog
from gui.widgets.import_result import show_import_result_banner
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


def format_snapshot_validation_issue(issue: object) -> str:
    return tr(
        "{player_name} · {category}/{stat}: Export {export_value} < boxscore {db_value}"
    ).format(
        player_name=getattr(issue, "player_name", ""),
        category=getattr(issue, "category", ""),
        stat=getattr(issue, "stat", ""),
        export_value=getattr(issue, "export_value", 0),
        db_value=getattr(issue, "db_value", 0),
    )


def build_snapshot_incomplete_message(
    validation: object, *, season: int, limit: int = 8
) -> str:
    issues = list(getattr(validation, "issues", ()))
    shown = issues[:limit]
    lines = [
        tr(
            "The exported stats look older than the imported boxscores. "
            "Export the final {season} season player stats from OOTP, then retry."
        ).format(season=season),
        "",
        tr("Showing {shown} of {total} issue(s):").format(
            shown=len(shown), total=len(issues)
        ),
    ]
    lines.extend(format_snapshot_validation_issue(issue) for issue in shown)
    return "\n".join(lines)

EVENT_TYPE_LABELS = dict(EVENT_TYPE_OPTIONS)

SEASON_FINALIZE_SOURCE = "season_final"
SEASON_FINALIZE_OUTCOME_COMPLETED = "completed"
SEASON_FINALIZE_OUTCOME_PARTIAL_SUCCESS = "partial_success"
SEASON_FINALIZE_OUTCOME_FAILED = "failed"
SEASON_FINALIZE_OUTCOME_CANCELLED = "cancelled"


@dataclass(frozen=True)
class SeasonFinalizeResult:
    outcome: str
    season: int
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    excluded: int = 0
    errors: int = 0
    unresolved: dict[str, int] = field(default_factory=dict)
    message: str = ""
    source: str = SEASON_FINALIZE_SOURCE

    def as_workflow_totals(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "created": self.created,
            "duplicates": self.duplicates,
            "excluded": self.excluded,
            "errors": self.errors,
        }

# Fixed positions of the compact Type/Source columns in _table_columns().
TYPE_COLUMN_INDEX = 4
SOURCE_COLUMN_INDEX = 5

MILESTONE_SOURCE_LABELS = {
    "boxscore_auto": "Boxscore automatic",
    "message_auto": "News automatic",
    "manual": "Manual entry",
    "season_final": "Season final judgement",
    "migration": "Migrated record",
    "validation": "Validation replay",
}


def event_type_display_label(event_type: str) -> str:
    """Human-readable label for a derived event type, matching the filter option text."""
    return tr(EVENT_TYPE_LABELS.get(event_type, "Other"))


def milestone_source(record: dict) -> str:
    """Return the explicit record source, with legacy is_manual/scope fallback."""
    source = str(record.get("source") or "").strip().lower()
    if source:
        return source
    if milestone_is_manual(record):
        return "manual"
    scope = str(record.get("scope") or "").lower()
    if scope in {"season", "season_ratio"} and not record.get("game_id"):
        return "season_final"
    return "boxscore_auto"


def source_display_label(source: str | bool) -> str:
    """Human-readable label for a milestone provenance source.

    Accepting bool preserves the old helper contract used by older tests and
    callers while the UI now prefers the explicit source value.
    """
    if isinstance(source, bool):
        return tr("Manual") if source else tr("Automatic")
    source_key = str(source or "").strip().lower()
    return tr(MILESTONE_SOURCE_LABELS.get(source_key, "Boxscore automatic"))


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
    record_source = milestone_source(record)
    if source == "automatic":
        return record_source != "manual"
    if source and record_source != source:
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


def _source_id_from_notes(notes: str) -> str:
    """Extract legacy message automation source:<id> notes for the detail panel."""
    for part in notes.split(";"):
        part = part.strip()
        if part.lower().startswith("source:"):
            return part.split(":", 1)[1].strip()
    return ""


def _table_columns() -> list[str]:
    return [
        tr("Date"),
        tr("Player or Team"),
        tr("Team"),
        tr("Milestone"),
        tr("Type"),
        tr("Source"),
    ]


class MilestoneView(QWidget):
    records_changed = pyqtSignal()
    import_finished = pyqtSignal(object)
    season_finalize_finished = pyqtSignal(object)
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
            self.grade_combo.addItem(tr(grade), grade)
        self.grade_combo.currentIndexChanged.connect(self.refresh)

        self.source_combo = QComboBox()
        self.source_combo.addItem(tr("All Sources"), "")
        for value, label in MILESTONE_SOURCE_LABELS.items():
            self.source_combo.addItem(tr(label), value)
        self.source_combo.currentIndexChanged.connect(self.refresh)

        self.advanced_filter_toggle = QToolButton()
        self.advanced_filter_toggle.setText(tr("Advanced filters"))
        self.advanced_filter_toggle.setCheckable(True)
        self.advanced_filter_toggle.setChecked(False)
        self.advanced_filter_toggle.setToolTip(tr("Expand or collapse this section."))
        self.advanced_filter_toggle.toggled.connect(self._set_advanced_filters_visible)

        self.reset_filters_button = QPushButton(tr("Reset Filters"))
        self.reset_filters_button.setObjectName("linkButton")
        self.reset_filters_button.clicked.connect(self.reset_filters)
        self.filter_summary_label = QLabel("")
        self.filter_summary_label.setObjectName("mutedLabel")
        self.filter_summary_label.setWordWrap(True)
        self.filter_summary_label.setStyleSheet(hint_style(TEXT_SECONDARY))

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
        for col_idx, width in ((0, 104), (2, 110), (TYPE_COLUMN_INDEX, 128), (SOURCE_COLUMN_INDEX, 142)):
            history_header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
            self.table_panel.table.setColumnWidth(col_idx, width)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.detail_title_label = QLabel(tr("Select a record to see details."))
        self.detail_title_label.setWordWrap(True)
        self.detail_title_label.setObjectName("detailTitle")
        self.detail_title_label.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.detail_description_label = QLabel("")
        self.detail_description_label.setWordWrap(True)
        self.detail_description_label.setStyleSheet(meta_panel_style())
        self.detail_facts_label = QLabel("")
        self.detail_facts_label.setWordWrap(True)
        self.detail_facts_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.detail_notes_label = QLabel("")
        self.detail_notes_label.setWordWrap(True)
        self.detail_notes_label.setStyleSheet(hint_style(TEXT_SECONDARY))
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
        more_menu.addAction(tr("Refresh"), self.refresh)
        self.more_menu_button.setMenu(more_menu)

        self.final_season_button = QPushButton(tr("Determine Final Season Records"))
        self.final_season_button.clicked.connect(self._record_season_ratio_milestones)

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

        basic_filter_grid = QGridLayout()
        basic_filter_grid.setHorizontalSpacing(10)
        basic_filter_grid.setVerticalSpacing(8)
        basic_filter_grid.addWidget(section_label(tr("Season")), 0, 0)
        basic_filter_grid.addWidget(self.season_spin, 0, 1)
        self.season_spin.setMaximumWidth(76)
        basic_filter_grid.addWidget(section_label(tr("Team")), 0, 2)
        basic_filter_grid.addWidget(self.team_filter, 0, 3)
        self.team_filter.setMinimumWidth(100)
        self.team_filter.setMaximumWidth(150)
        basic_filter_grid.addWidget(section_label(tr("Search")), 0, 4)
        basic_filter_grid.addWidget(self.table_panel.filter_bar.search_input, 0, 5)
        basic_filter_grid.addWidget(section_label(tr("Event Type")), 1, 0)
        basic_filter_grid.addWidget(self.event_type_combo, 1, 1, 1, 3)
        basic_filter_grid.addWidget(self.reset_filters_button, 1, 4)
        basic_filter_grid.addWidget(self.advanced_filter_toggle, 1, 5)
        basic_filter_grid.setColumnStretch(5, 1)

        self.advanced_filter_widget = QWidget()
        advanced_filter_grid = QGridLayout(self.advanced_filter_widget)
        advanced_filter_grid.setContentsMargins(0, 0, 0, 0)
        advanced_filter_grid.setHorizontalSpacing(10)
        advanced_filter_grid.setVerticalSpacing(8)
        advanced_filter_grid.addWidget(section_label(tr("Subject")), 0, 0)
        advanced_filter_grid.addWidget(self.subject_combo, 0, 1)
        self.subject_combo.setMaximumWidth(120)
        advanced_filter_grid.addWidget(section_label(tr("Scope")), 0, 2)
        advanced_filter_grid.addWidget(self.scope_combo, 0, 3)
        self.scope_combo.setMaximumWidth(140)
        advanced_filter_grid.addWidget(section_label(tr("Grade")), 0, 4)
        advanced_filter_grid.addWidget(self.grade_combo, 0, 5)
        advanced_filter_grid.addWidget(section_label(tr("Source")), 1, 0)
        advanced_filter_grid.addWidget(self.source_combo, 1, 1, 1, 3)
        advanced_filter_grid.setColumnStretch(5, 1)
        self.advanced_filter_widget.setVisible(False)

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
        action_row.addWidget(self.final_season_button)
        action_row.addWidget(self.more_menu_button)

        hint = QLabel(tr("F2: Edit · Del: Delete · Double-click: Game Log"))
        hint.setObjectName("mutedLabel")

        filter_card = CardPanel()
        filter_card.content_layout.addLayout(basic_filter_grid)
        filter_card.content_layout.addWidget(self.advanced_filter_widget)
        filter_card.content_layout.addWidget(self.filter_summary_label)
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

        detail_action_row = QHBoxLayout()
        detail_action_row.addWidget(self.player_detail_button)
        detail_action_row.addWidget(self.game_log_button)
        detail_action_row.addStretch()
        detail_action_row.addWidget(self.edit_button)
        detail_action_row.addWidget(self.delete_button)
        self.meta_card = CardPanel(tr("Selected record details"))
        self.meta_card.content_layout.addWidget(self.detail_title_label)
        self.meta_card.content_layout.addWidget(self.detail_description_label)
        self.meta_card.content_layout.addWidget(self.detail_facts_label)
        self.meta_card.content_layout.addWidget(self.detail_notes_label)
        self.meta_card.content_layout.addLayout(detail_action_row)
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

    def _set_advanced_filters_visible(self, visible: bool) -> None:
        self.advanced_filter_widget.setVisible(visible)
        self.advanced_filter_toggle.setText(
            tr("Hide advanced filters") if visible else tr("Advanced filters")
        )

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
        self._import_worker.workflow_finished.connect(self._on_import_finished)
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

        self.import_finished.emit(payload)
        self.refresh()

        if payload.outcome == SEASON_FINALIZE_OUTCOME_CANCELLED:
            self.banner.show_info(payload.message)
        elif payload.outcome == SEASON_FINALIZE_OUTCOME_FAILED:
            self.banner.show_error(
                payload.message,
                [
                    (
                        tr("View Errors ({count})").format(count=payload.errors),
                        lambda: ImportErrorsDialog(payload.batch.errors, self).exec(),
                    )
                ]
                if payload.batch.errors
                else None,
            )
        else:
            show_import_result_banner(
                self.banner,
                payload,
                on_view_milestones=lambda: MilestoneAchievedDialog(payload.milestones, self).exec(),
                on_view_errors=lambda: ImportErrorsDialog(
                    payload.batch.errors, self
                ).exec(),
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

    def stop_import_worker(self) -> None:
        """Cancel and join a running import worker.

        Called on shutdown so Qt never destroys a still-running QThread
        (which otherwise logs "QThread: Destroyed while thread is still
        running" and can crash on some platforms).
        """
        worker = self._import_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.quit()
            worker.wait(5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.stop_import_worker()
        super().closeEvent(event)

    def refresh(self) -> None:
        preferred_record_id = self._highlight_id or self._selected_record_id_from_table()
        if preferred_record_id is None:
            preferred_record_id = self._selected_record_id
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
            event_type = milestone_event_type(record, milestone)
            type_label = event_type_display_label(event_type)
            record_source = milestone_source(record)
            is_manual = record_source == "manual"
            source_label = source_display_label(record_source)
            values = [
                record.get("achieved_date") or "",
                display_name,
                affiliation,
                label,
                type_label,
                source_label,
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
                if col_idx == TYPE_COLUMN_INDEX:
                    item.setToolTip(type_label)
                elif col_idx == SOURCE_COLUMN_INDEX:
                    item.setToolTip(source_label)
                elif col_idx == 3:
                    details = [label]
                    if korean_name:
                        details.append(tr("Korean name: {value}").format(value=korean_name))
                    if record.get("description"):
                        details.append(str(record.get("description")))
                    item.setToolTip("\n".join(details))

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
                    if is_manual and col_idx in (3, SOURCE_COLUMN_INDEX):
                        item.setForeground(QColor(AMBER_TEXT))

                if is_highlighted:
                    item.setBackground(QColor("#3a2f00"))

                self.table_panel.table.setItem(row_idx, col_idx, item)
        self.table_panel.table.setSortingEnabled(True)
        if preferred_record_id is not None:
            restored = select_record_row(self.table_panel.table, preferred_record_id)
            if not restored and self._records:
                self.table_panel.table.selectRow(0)
            if self._highlight_id is not None:
                self._highlight_id = None
        elif self._records:
            self.table_panel.table.selectRow(0)
        if not self._records:
            self._highlight_id = None
            self._update_meta_panel()
        self._update_selection_actions()

    def _filters_active(self) -> bool:
        return any(
            (
                (self.subject_combo.currentData() or "all") != "all",
                bool(self.team_filter.currentData()),
                bool(self.scope_combo.currentData()),
                self.season_spin.value() > 0,
                bool(self.table_panel.filter_bar.search_input.text().strip()),
                bool(self.event_type_combo.currentData()),
                bool(self.grade_combo.currentData()),
                bool(self.source_combo.currentData()),
            )
        )

    def _active_filter_labels(self) -> list[str]:
        labels: list[str] = []
        if (self.subject_combo.currentData() or "all") != "all":
            labels.append(tr("Subject: {value}").format(value=self.subject_combo.currentText()))
        if self.team_filter.currentData():
            labels.append(tr("Team: {value}").format(value=self.team_filter.currentText()))
        if self.scope_combo.currentData():
            labels.append(tr("Scope: {value}").format(value=self.scope_combo.currentText()))
        if self.season_spin.value() > 0:
            labels.append(tr("Season: {value}").format(value=self.season_spin.value()))
        search = self.table_panel.filter_bar.search_input.text().strip()
        if search:
            labels.append(tr("Search: {value}").format(value=search))
        if self.event_type_combo.currentData():
            labels.append(tr("Event Type: {value}").format(value=self.event_type_combo.currentText()))
        if self.grade_combo.currentData():
            labels.append(tr("Grade: {value}").format(value=self.grade_combo.currentText()))
        if self.source_combo.currentData():
            labels.append(tr("Source: {value}").format(value=self.source_combo.currentText()))
        return labels

    def _update_filter_summary(self, shown_count: int, total_count: int) -> None:
        active_labels = self._active_filter_labels()
        self.reset_filters_button.setEnabled(bool(active_labels))
        if not total_count:
            self.filter_summary_label.setText(tr("No milestone records available."))
            return
        base = tr("Showing {shown} of {total} records").format(
            shown=shown_count, total=total_count
        )
        if active_labels:
            self.filter_summary_label.setText(base + " - " + " / ".join(active_labels))
        else:
            self.filter_summary_label.setText(base)

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

    def _season_export_paths(self) -> tuple[Path | None, Path | None]:
        """Expected OOTP export files for the season-close ratio judgement."""
        directory = self.settings.import_export_dir or self.settings.initial_stats_dir
        if not directory:
            return None, None
        base = Path(directory)
        return (
            base / SNAPSHOT_BATTING_FILENAME,
            base / SNAPSHOT_PITCHING_FILENAME,
        )

    def _confirm_season_ratio_export(
        self, season: int, batting_path: Path | None, pitching_path: Path | None
    ) -> bool:
        """Ask before judging; missing files are handled after Continue."""
        missing = [
            path
            for path in (batting_path, pitching_path)
            if path is None or not path.is_file()
        ]
        box = QMessageBox(self)
        box.setWindowTitle(tr("Determine Final Season Records"))
        if batting_path is None or pitching_path is None or missing:
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(
                tr(
                    "Export the {season} season player stats from OOTP before continuing.\n\n"
                    "If you still need to export, select Cancel. If the stats files "
                    "already exist, select Continue."
                ).format(season=season)
            )
            if batting_path is None or pitching_path is None:
                box.setInformativeText(
                    tr("No export folder is configured. Set it in Settings and retry.")
                )
            else:
                box.setInformativeText(
                    "\n".join(tr("Not found: {path}").format(path=p) for p in missing)
                )
        else:
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(
                tr(
                    "{season} season AVG/OBP/SLG/OPS/ERA milestones will be judged from "
                    "the exported OOTP stats files.\n\n"
                    "If you still need to export, select Cancel. If these files are the "
                    "latest export, select Continue."
                ).format(season=season)
            )
            box.setInformativeText(
                "\n".join(str(path) for path in (batting_path, pitching_path))
            )
        box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        continue_button = box.addButton(tr("Continue"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(continue_button)
        box.exec()
        return box.clickedButton() is continue_button

    def _season_finalize_record_count(self, season: int) -> int:
        row = self.aggregator.conn.execute(
            """
            SELECT COUNT(*) FROM milestone_records
            WHERE source = ? AND season = ?
            """,
            (SEASON_FINALIZE_SOURCE, season),
        ).fetchone()
        return int(row[0] if row is not None else 0)

    def _emit_season_finalize_result(
        self, result: SeasonFinalizeResult
    ) -> SeasonFinalizeResult:
        self.season_finalize_finished.emit(result)
        return result

    def _record_season_ratio_milestones(self) -> SeasonFinalizeResult:
        season = self.season_spin.value() or self.settings.current_season
        if season <= 0:
            QMessageBox.information(
                self,
                tr("Select Season"),
                tr("Please select a season year in the season filter and try again."),
            )
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_FAILED,
                    season=season,
                    errors=1,
                    unresolved={"errors": 1},
                    message=tr("A valid season is required."),
                )
            )
        batting_path, pitching_path = self._season_export_paths()
        if not self._confirm_season_ratio_export(season, batting_path, pitching_path):
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_CANCELLED,
                    season=season,
                    message=tr("Season finalization was cancelled."),
                )
            )
        try:
            importer = InitialImporter(self.aggregator)
            snapshot = importer.read_season_snapshot(
                season=season,
                batting_path=batting_path,
                pitching_path=pitching_path,
            )
        except ExportSnapshotError as exc:
            QMessageBox.warning(self, tr("Export File Problem"), str(exc))
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_FAILED,
                    season=season,
                    errors=1,
                    unresolved={"errors": 1},
                    message=str(exc),
                )
            )
        validation = importer.validate_season_snapshot(snapshot)
        if validation.status == "no_current_season":
            message = tr(
                "The export files do not contain current {season} season rows. "
                "Export both batting and pitching player stats from OOTP, then retry."
            ).format(season=season)
            QMessageBox.warning(self, tr("No Season Data"), message)
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_FAILED,
                    season=season,
                    errors=1,
                    unresolved={"errors": 1},
                    message=message,
                )
            )
        if validation.status == "incomplete":
            message = build_snapshot_incomplete_message(validation, season=season)
            QMessageBox.warning(self, tr("Export File Problem"), message)
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_FAILED,
                    season=season,
                    errors=1,
                    unresolved={"errors": len(getattr(validation, "issues", ())) or 1},
                    message=message,
                )
            )

        default_date = f"{season}-12-31"
        date_str, ok = QInputDialog.getText(
            self,
            tr("Enter In-Game Date"),
            tr("Enter the in-game date for the season-end records (YYYY-MM-DD):"),
            text=default_date,
        )
        if not ok:
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_CANCELLED,
                    season=season,
                    message=tr("Season finalization was cancelled."),
                )
            )
        date_str = date_str.strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            message = tr("Please enter the date in YYYY-MM-DD format.")
            QMessageBox.warning(self, tr("Invalid Date"), message)
            return self._emit_season_finalize_result(
                SeasonFinalizeResult(
                    outcome=SEASON_FINALIZE_OUTCOME_FAILED,
                    season=season,
                    errors=1,
                    unresolved={"errors": 1},
                    message=message,
                )
            )

        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        before_count = self._season_finalize_record_count(season)
        try:
            achievements = checker.check_season_ratios(
                season,
                achieved_date=date_str,
                totals_override=snapshot.as_totals_override(),
            )
            recorded = int(checker.record_achievements(achievements) or 0)
        except Exception as exc:
            created = max(0, self._season_finalize_record_count(season) - before_count)
            processed = len(locals().get("achievements", ()))
            result = SeasonFinalizeResult(
                outcome=(
                    SEASON_FINALIZE_OUTCOME_PARTIAL_SUCCESS
                    if created > 0
                    else SEASON_FINALIZE_OUTCOME_FAILED
                ),
                season=season,
                processed=processed,
                created=created,
                duplicates=max(0, processed - created),
                errors=1,
                unresolved={"errors": 1},
                message=str(exc),
            )
            QMessageBox.warning(self, tr("Season Finalization Failed"), str(exc))
            if created:
                self.refresh()
                self.records_changed.emit()
            return self._emit_season_finalize_result(result)

        processed = len(achievements)
        result = SeasonFinalizeResult(
            outcome=SEASON_FINALIZE_OUTCOME_COMPLETED,
            season=season,
            processed=processed,
            created=recorded,
            duplicates=max(0, processed - recorded),
            message=tr("{season} season finalization completed.").format(season=season),
        )
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
        return self._emit_season_finalize_result(result)

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
        self.edit_button.setToolTip(
            "" if has_selection else tr("Select a record to edit.")
        )
        self.delete_button.setToolTip(
            "" if has_selection else tr("Select a record to delete.")
        )

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
            self.detail_title_label.setText(tr("Select a record to see details."))
            self.detail_description_label.setText("")
            self.detail_facts_label.setText("")
            self.detail_notes_label.setText("")
            self.game_log_button.setEnabled(False)
            self.player_detail_button.setEnabled(False)
            self.log_hint_panel.hide()
            self.meta_card.setVisible(False)
            return
        self.meta_card.setVisible(True)
        self._selected_record_id = int(record["id"])
        milestone = self.milestones.get_by_key(str(record.get("milestone_key") or ""))
        label = (
            milestone.label
            if milestone
            else record.get("milestone_label", record.get("milestone_key", ""))
        )
        is_team = int(record.get("player_id") or 0) == 0 and bool(record.get("team"))
        target = str(record.get("team") or "") if is_team else str(record.get("player_name") or "")
        self.detail_title_label.setText(f"{target} · {label}" if target else str(label))

        description_parts: list[str] = []
        if milestone is not None and getattr(milestone, "description_template", ""):
            description_parts.append(str(getattr(milestone, "description_template")))
        if record.get("description"):
            description_parts.append(str(record.get("description")))
        self.detail_description_label.setText("\n".join(description_parts))

        facts: list[str] = []
        if record.get("achieved_value") is not None:
            facts.append(tr("Value: {value}").format(value=record["achieved_value"]))
        games = record.get("games_at_achievement")
        if games is not None:
            facts.append(tr("Games at achievement: {value}").format(value=games))
        if record.get("season"):
            facts.append(tr("Season: {season}").format(season=record["season"]))
        if record.get("scope"):
            facts.append(tr("Scope: {value}").format(value=record["scope"]))
        facts.append(tr("Type: {value}").format(
            value=event_type_display_label(milestone_event_type(record, milestone))
        ))
        facts.append(tr("Source: {value}").format(
            value=source_display_label(milestone_source(record))
        ))
        if record.get("game_id"):
            facts.append(tr("Game ID: {game_id}").format(game_id=record["game_id"]))
        if record.get("opponent_team"):
            facts.append(tr("Opponent: {value}").format(value=record["opponent_team"]))
        if record.get("opponent_player"):
            facts.append(tr("Opposing player: {value}").format(value=record["opponent_player"]))
        source_id = record.get("source_id") or _source_id_from_notes(str(record.get("notes") or ""))
        if source_id:
            facts.append(tr("Original source: {value}").format(value=source_id))
        self.detail_facts_label.setText(" · ".join(facts))

        notes = str(record.get("notes") or "").strip()
        self.detail_notes_label.setText(
            tr("Notes: {value}").format(value=notes) if notes else tr("No notes.")
        )
        self.game_log_button.setEnabled(bool(record.get("game_id")))
        self.player_detail_button.setEnabled(self._record_has_player(record))
        self.game_log_button.setToolTip(
            "" if self.game_log_button.isEnabled() else tr("No linked game is available.")
        )
        self.player_detail_button.setToolTip(
            "" if self.player_detail_button.isEnabled() else tr("No linked player is available.")
        )
        self.edit_button.setToolTip(
            "" if self.edit_button.isEnabled() else tr("Select a record to edit.")
        )
        self.delete_button.setToolTip(
            "" if self.delete_button.isEnabled() else tr("Select a record to delete.")
        )
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
