"""Initial OOTP save folder and league selection screen."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QFrame,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    AppSettings,
    DetectedSaveRoot,
    SaveEntry,
    SettingsManager,
    detect_save_roots,
    infer_ootp_version_from_path,
    is_valid_save_root,
    resolve_data_path,
    scan_saves,
)
from core.i18n import tr
from core.db.reset import (
    format_save_data_summary,
    reset_save_database,
    summarize_save_database,
)
from gui.widgets.tracked_teams_widget import TrackedTeamsWidget
from gui.widgets.card_panel import CardPanel, section_label, tool_row
from gui.theme import SLATE_500, TEXT_MUTED


class SetupView(QWidget):
    """First-run and league selection UI."""

    setup_completed = pyqtSignal(object)  # AppSettings
    milestones_changed = pyqtSignal()
    bundle_updates_changed = pyqtSignal()
    save_database_reset_prepare = pyqtSignal()
    save_database_reset = pyqtSignal()
    boxscore_reimported = pyqtSignal(str)

    def __init__(
        self,
        settings_manager: SettingsManager,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
        *,
        embedded: bool = False,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.settings = settings or settings_manager.load()
        self._embedded = embedded
        self._detected_roots: list[DetectedSaveRoot] = []
        self._save_entries: list[SaveEntry] = []
        self._selected_version: int | None = None

        title = QLabel("OOTP Milestone Tracker")
        title.setObjectName("pageTitle")

        self.save_root_input = QLineEdit()
        self.save_root_input.setPlaceholderText(tr("OOTP saved_games folder path"))
        self.browse_button = QPushButton(tr("Verify Path") if embedded else tr("Browse"))
        self.browse_button.clicked.connect(self._browse_save_root)

        self.auto_radio = QRadioButton(tr("Auto-detected"))
        self.manual_radio = QRadioButton(tr("Manual"))
        self.detection_status = QLabel("")
        self.detection_status.setWordWrap(True)
        self.detection_status.setObjectName("mutedLabel")

        self.detected_roots_combo = QComboBox()
        self.detected_roots_combo.setVisible(False)
        self.detected_roots_combo.currentIndexChanged.connect(self._on_detected_root_changed)

        self.league_combo = QComboBox()
        self.refresh_button = QPushButton(tr("Refresh"))
        self.refresh_button.clicked.connect(self._refresh_leagues)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setValue(self.settings.current_season)
        self.season_spin.setToolTip(
            tr(
                "The season year currently in progress in OOTP.\n"
                "Used for boxscore import filtering, initial stats import, and milestone evaluation."
            )
        )

        self.tracked_teams_widget = TrackedTeamsWidget(
            self, checkbox_mode=embedded
        )
        self.tracked_teams_widget.load_from_settings(self.settings)

        self.season_games_spin = QSpinBox()
        self.season_games_spin.setRange(1, 200)
        self.season_games_spin.setValue(self.settings.season_games_total)

        self.language_combo = QComboBox()
        self.language_combo.addItem("한국어 (Korean)", "ko")
        self.language_combo.addItem("English", "en")
        lang_index = self.language_combo.findData(getattr(self.settings, "language", "ko"))
        if lang_index >= 0:
            self.language_combo.setCurrentIndex(lang_index)

        self.korean_names_button = QPushButton(tr("Open Pending Mappings"))
        self.korean_names_button.clicked.connect(self._open_korean_name_mapping)
        self.korean_badge = QLabel("0")
        self.korean_badge.setObjectName("badgeLabel")
        self.korean_badge.setVisible(False)
        self._refresh_korean_names_button()

        self.bundle_updates_status = QLabel()
        self.bundle_updates_status.setWordWrap(True)
        self.bundle_updates_status.setObjectName("mutedLabel")
        self.bundle_updates_button = QPushButton(tr("Run Merge Update"))
        self.bundle_updates_button.clicked.connect(self._open_bundle_updates)

        self.milestones_button = QPushButton(tr("Edit Milestone Definitions"))
        self.milestones_button.clicked.connect(self._open_milestone_definitions)

        self.selected_path_label = QLabel("")
        self.selected_path_label.setWordWrap(True)
        self.selected_path_label.setObjectName("mutedLabel")

        self.confirm_button = QPushButton(
            tr("Save All Settings & Refresh Data") if embedded else tr("Confirm & Start")
        )
        self.confirm_button.clicked.connect(self._confirm)
        self.confirm_button.setDefault(True)
        if embedded:
            self.confirm_button.setObjectName("primaryButton")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        if not embedded:
            layout.addWidget(title)
            layout.addSpacing(4)
            self._build_first_run_layout(layout)
        else:
            self._build_embedded_layout(layout)

        self.save_root_input.textChanged.connect(self._on_save_root_changed)
        self.league_combo.currentIndexChanged.connect(self._update_selected_path_label)
        self.manual_radio.toggled.connect(self._on_mode_changed)

        if embedded and self.settings.active_save_path:
            self.manual_radio.setChecked(True)
            self._restore_saved_values()
        else:
            self._run_auto_detection()
            self._restore_saved_values()

        self.refresh_bundle_updates_status()

    def _build_first_run_layout(self, layout: QVBoxLayout) -> None:
        # ── Left card: OOTP Integration ──────────────────────────────────────
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self.save_root_input, stretch=1)
        path_row.addWidget(self.browse_button)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_radio)
        mode_row.addWidget(self.manual_radio)
        mode_row.addStretch()

        league_row = QHBoxLayout()
        league_row.addWidget(self.league_combo, stretch=1)
        league_row.addWidget(self.refresh_button)

        season_row = QHBoxLayout()
        season_row.setSpacing(8)
        season_row.addWidget(section_label(tr("Season Year")))
        season_row.addWidget(self.season_spin)
        season_row.addStretch()

        ootp_card = CardPanel(tr("📁  OOTP Integration"))
        ootp_card.content_layout.addWidget(section_label(tr("saved_games Folder")))
        ootp_card.content_layout.addLayout(path_row)
        ootp_card.content_layout.addWidget(self.detected_roots_combo)
        ootp_card.content_layout.addLayout(mode_row)
        ootp_card.content_layout.addWidget(self.detection_status)
        ootp_card.content_layout.addSpacing(8)
        ootp_card.content_layout.addWidget(section_label(tr("League")))
        ootp_card.content_layout.addLayout(league_row)
        ootp_card.content_layout.addSpacing(8)
        ootp_card.content_layout.addLayout(season_row)
        ootp_card.content_layout.addWidget(self.selected_path_label)
        ootp_card.content_layout.addStretch()

        # ── Right top card: Tracking Settings ────────────────────────────────
        teams_header = QHBoxLayout()
        teams_header.addWidget(section_label(tr("Tracked Team List")))
        teams_header.addStretch()
        add_team_link = QPushButton(tr("+ Add Team Manually"))
        add_team_link.setObjectName("linkButton")
        add_team_link.clicked.connect(self.tracked_teams_widget.add_custom_team_dialog)
        teams_header.addWidget(add_team_link)

        season_lang_row = QHBoxLayout()
        season_lang_row.setSpacing(8)
        season_lang_row.addWidget(section_label(tr("Season Games")))
        season_lang_row.addWidget(self.season_games_spin)
        season_lang_row.addSpacing(16)
        season_lang_row.addWidget(section_label(tr("Language")))
        season_lang_row.addWidget(self.language_combo)
        season_lang_row.addStretch()

        tracking_card = CardPanel(tr("⚙️  Tracking Settings"))
        tracking_card.content_layout.addLayout(teams_header)
        tracking_card.content_layout.addWidget(self.tracked_teams_widget)
        tracking_card.content_layout.addLayout(season_lang_row)

        # ── Right bottom card: Tools ─────────────────────────────────────────
        tools_card = CardPanel(tr("🛠️  Tools"))
        tools_card.add_widget(
            tool_row(
                tr("Korean Name Auto-mapping"),
                tr("Processes pending romanized name → Korean conversion items."),
                self.korean_names_button,
            )
        )
        tools_card.add_widget(
            tool_row(
                tr("Update App Reference Files"),
                tr("Merges local milestone ruleset and Korean name mapping patches."),
                self.bundle_updates_button,
            )
        )
        tools_card.content_layout.addWidget(self.bundle_updates_status)
        tools_card.add_widget(
            tool_row(
                tr("Edit Milestone Criteria"),
                tr("Defines milestone types and grade thresholds in milestones.csv."),
                self.milestones_button,
            )
        )

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        right_col.addWidget(tracking_card)
        right_col.addWidget(tools_card)
        right_col.addStretch()

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(ootp_card, stretch=1)
        columns.addLayout(right_col, stretch=1)

        layout.addLayout(columns, stretch=1)
        layout.addWidget(self.confirm_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _build_embedded_layout(self, layout: QVBoxLayout) -> None:
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(section_label(tr("OOTP SAVED_GAMES Root")), stretch=0)
        path_row.addWidget(self.save_root_input, stretch=1)
        path_row.addWidget(self.browse_button)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_radio)
        mode_row.addWidget(self.manual_radio)
        mode_row.addStretch()

        league_season_row = QHBoxLayout()
        league_season_row.setSpacing(12)
        league_col = QVBoxLayout()
        league_col.setSpacing(4)
        league_col.addWidget(section_label(tr("Scanned Save Leagues")))
        league_btns = QHBoxLayout()
        league_btns.addWidget(self.league_combo, stretch=1)
        league_btns.addWidget(self.refresh_button)
        league_col.addLayout(league_btns)
        season_col = QVBoxLayout()
        season_col.setSpacing(4)
        season_col.addWidget(section_label(tr("Current Active Season")))
        season_col.addWidget(self.season_spin)
        league_season_row.addLayout(league_col, stretch=1)
        league_season_row.addLayout(season_col, stretch=0)

        teams_header = QHBoxLayout()
        teams_header.addWidget(section_label(tr("Tracked Team List")))
        teams_header.addStretch()
        add_team_link = QPushButton(tr("+ Add Team Manually"))
        add_team_link.setObjectName("linkButton")
        add_team_link.clicked.connect(self.tracked_teams_widget.add_custom_team_dialog)
        teams_header.addWidget(add_team_link)

        season_games_row = QHBoxLayout()
        season_games_row.setSpacing(8)
        season_games_row.addWidget(section_label(tr("Total Season Games")))
        season_games_row.addWidget(self.season_games_spin)
        season_games_row.addSpacing(16)
        season_games_row.addWidget(section_label(tr("Language")))
        season_games_row.addWidget(self.language_combo)
        season_games_row.addStretch()

        ootp_card = CardPanel(tr("📁  OOTP Integration Settings"))
        ootp_card.content_layout.addLayout(path_row)
        ootp_card.content_layout.addWidget(self.detected_roots_combo)
        ootp_card.content_layout.addLayout(mode_row)
        ootp_card.content_layout.addWidget(self.detection_status)
        ootp_card.content_layout.addLayout(league_season_row)
        ootp_card.content_layout.addLayout(teams_header)
        ootp_card.content_layout.addWidget(self.tracked_teams_widget)
        ootp_card.content_layout.addLayout(season_games_row)
        ootp_card.content_layout.addWidget(self.selected_path_label)

        self._init_db_reset_widgets()

        tools_card = CardPanel(tr("🛠️  Advanced Modules & Data Tools"))
        tools_card.add_widget(
            tool_row(
                tr("Korean Name Auto-mapping"),
                tr("Processes pending romanized name → Korean conversion items."),
                self.korean_names_button,
                badge=self.korean_badge,
            )
        )
        tools_card.add_widget(
            tool_row(
                tr("Edit Milestone Criteria"),
                tr("Defines milestone types and grade thresholds in milestones.csv."),
                self.milestones_button,
            )
        )
        tools_card.add_widget(
            tool_row(
                tr("Update App Reference Files"),
                tr("Merges local milestone ruleset and Korean name mapping patches."),
                self.bundle_updates_button,
            )
        )
        tools_card.add_widget(self._build_dev_tools_panel())

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(ootp_card, stretch=1)
        columns.addWidget(tools_card, stretch=1)
        layout.addLayout(columns, stretch=1)
        layout.addWidget(self.confirm_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _init_db_reset_widgets(self) -> None:
        self.db_summary_label = QLabel()
        self.db_summary_label.setWordWrap(True)
        self.db_summary_label.setObjectName("mutedLabel")
        self.db_path_label = QLabel()
        self.db_path_label.setWordWrap(True)
        self.db_path_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.refresh_db_summary_button = QPushButton(tr("Refresh Status"))
        self.refresh_db_summary_button.clicked.connect(self._refresh_database_summary)
        self.reset_db_button = QPushButton(tr("🚨 Full DB Reset"))
        self.reset_db_button.setObjectName("dangerButton")
        self.reset_db_button.clicked.connect(self._reset_save_database)
        self.dev_reimport_button = QPushButton(tr("🔄 Re-import Individual Boxscores"))
        self.dev_reimport_button.clicked.connect(self._open_dev_boxscore_reimport)
        self._refresh_database_summary()

    def _build_dev_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("toolRow")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        dev_title = QLabel(tr("Developer Tools"))
        dev_title.setObjectName("toolRowTitle")
        layout.addWidget(dev_title)

        dev_buttons = QHBoxLayout()
        dev_buttons.setSpacing(8)
        dev_buttons.addWidget(self.dev_reimport_button, stretch=1)
        dev_buttons.addWidget(self.reset_db_button)
        layout.addLayout(dev_buttons)

        layout.addWidget(self.db_summary_label)
        layout.addWidget(self.db_path_label)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_row.addWidget(self.refresh_db_summary_button)
        layout.addLayout(refresh_row)
        return panel

    def refresh_bundle_updates_status(self) -> None:
        from core.config.bundle_updates import scan_pending_updates

        report = scan_pending_updates()
        if report.total:
            self.bundle_updates_status.setText(
                tr("{count} new items available (app v{version})").format(
                    count=report.total, version=report.app_version
                )
            )
            self.bundle_updates_status.setStyleSheet("color: #c0392b;")
            self.bundle_updates_button.setEnabled(True)
            if self._embedded:
                self.bundle_updates_button.setText(tr("Run Merge Update"))
                self.bundle_updates_button.setObjectName("dangerButton")
            else:
                self.bundle_updates_button.setText(
                    tr("Update Reference Files... ({count})").format(count=report.total)
                )
                self.bundle_updates_button.setObjectName("")
        else:
            self.bundle_updates_status.setText(tr("All reference files are up to date."))
            self.bundle_updates_status.setStyleSheet(f"color: {SLATE_500};")
            self.bundle_updates_button.setEnabled(False)
            if self._embedded:
                self.bundle_updates_button.setText(tr("Run Merge Update"))
            else:
                self.bundle_updates_button.setText(tr("Update Reference Files..."))
            self.bundle_updates_button.setObjectName("")
        self.bundle_updates_button.style().unpolish(self.bundle_updates_button)
        self.bundle_updates_button.style().polish(self.bundle_updates_button)

    def _run_auto_detection(self) -> None:
        self._detected_roots = detect_save_roots()
        if not self._detected_roots:
            self.auto_radio.setEnabled(False)
            self.manual_radio.setChecked(True)
            self.detection_status.setText(
                tr("Auto-detection failed. Use [Browse] to select the saved_games folder manually.")
            )
            return

        self.auto_radio.setEnabled(True)
        self.auto_radio.setChecked(True)
        self.detection_status.setText(
            tr("Auto-detection successful: {count} path(s) found.").format(
                count=len(self._detected_roots)
            )
        )

        if len(self._detected_roots) > 1:
            self.detected_roots_combo.setVisible(True)
            self.detected_roots_combo.blockSignals(True)
            self.detected_roots_combo.clear()
            for item in self._detected_roots:
                self.detected_roots_combo.addItem(
                    f"OOTP {item.ootp_version} — {item.path}",
                    str(item.path),
                )
            self.detected_roots_combo.blockSignals(False)
        else:
            self.detected_roots_combo.setVisible(False)

        if not self.settings.ootp_save_root:
            first = self._detected_roots[0]
            self._apply_save_root(str(first.path), first.ootp_version, from_auto=True)

    def _restore_saved_values(self) -> None:
        if self.settings.ootp_save_root:
            if is_valid_save_root(self.settings.ootp_save_root):
                self.manual_radio.setChecked(True)
                self.save_root_input.setText(self.settings.ootp_save_root)
            else:
                self.save_root_input.setText(self.settings.ootp_save_root)

        self._refresh_leagues()

        if self.settings.active_save:
            index = self.league_combo.findText(self.settings.active_save)
            if index >= 0:
                self.league_combo.setCurrentIndex(index)

        self.season_spin.setValue(self.settings.current_season)
        self.season_games_spin.setValue(self.settings.season_games_total)
        self.tracked_teams_widget.load_from_settings(self.settings)

    def _browse_save_root(self) -> None:
        start_dir = self.save_root_input.text().strip() or str(Path.home() / "Documents")
        selected = QFileDialog.getExistingDirectory(
            self,
            tr("Select OOTP saved_games folder"),
            start_dir,
        )
        if not selected:
            return

        self.manual_radio.setChecked(True)
        self.save_root_input.setText(selected)
        self._validate_and_refresh(selected, show_errors=True)

    def _on_mode_changed(self, manual: bool) -> None:
        if not manual and self._detected_roots:
            index = self.detected_roots_combo.currentIndex()
            if index >= 0 and self.detected_roots_combo.isVisible():
                self._on_detected_root_changed(index)
            else:
                first = self._detected_roots[0]
                self._apply_save_root(str(first.path), first.ootp_version, from_auto=True)

    def _on_detected_root_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._detected_roots):
            return
        if not self.auto_radio.isChecked():
            return
        item = self._detected_roots[index]
        self._apply_save_root(str(item.path), item.ootp_version, from_auto=True)

    def _on_save_root_changed(self, text: str) -> None:
        if self.manual_radio.isChecked():
            self._validate_and_refresh(text.strip(), show_errors=False)

    def _apply_save_root(self, path: str, version: int | None, *, from_auto: bool) -> None:
        self.save_root_input.blockSignals(True)
        self.save_root_input.setText(path)
        self.save_root_input.blockSignals(False)
        self._selected_version = version
        if from_auto:
            self.detection_status.setText(
                tr("Auto-detected: OOTP {version} — {path}").format(version=version, path=path)
            )
        self._refresh_leagues()

    def _validate_and_refresh(self, path: str, *, show_errors: bool) -> None:
        if not path:
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            return

        if not is_valid_save_root(path):
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            if show_errors:
                QMessageBox.warning(
                    self,
                    tr("Invalid Path"),
                    tr(
                        "The selected folder is not an OOTP saved_games directory.\n\n"
                        "Make sure you selected the saved_games folder.\n"
                        "(It must contain league folders or .lg folders.)"
                    ),
                )
            else:
                self.detection_status.setText(tr("Invalid saved_games path."))
            return

        self._selected_version = None
        self.detection_status.setText(tr("Valid saved_games path."))
        self._refresh_leagues()

    def _refresh_leagues(self) -> None:
        path = self.save_root_input.text().strip()
        if not path or not is_valid_save_root(path):
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            return

        self._save_entries = scan_saves(path)
        previous = self.league_combo.currentText()

        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        for entry in self._save_entries:
            self.league_combo.addItem(entry.name, str(entry.path))
        self.league_combo.blockSignals(False)

        if not self._save_entries:
            self.detection_status.setText(tr("No valid league folders found under saved_games."))
            self._update_selected_path_label()
            return

        restore_index = self.league_combo.findText(previous)
        if restore_index >= 0:
            self.league_combo.setCurrentIndex(restore_index)
        elif self.settings.active_save:
            saved_index = self.league_combo.findText(self.settings.active_save)
            if saved_index >= 0:
                self.league_combo.setCurrentIndex(saved_index)

        self._update_selected_path_label()

    def _update_selected_path_label(self) -> None:
        index = self.league_combo.currentIndex()
        if index >= 0:
            path = self.league_combo.itemData(index)
            self.selected_path_label.setText(str(path) if path else "")
        else:
            self.selected_path_label.setText(tr("(Please select a league)"))
        if hasattr(self, "db_summary_label"):
            self._refresh_database_summary()

    def _open_dev_boxscore_reimport(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(
                self, tr("League Required"), tr("Please select a league to re-import first.")
            )
            return

        db_path = resolve_data_path(settings.db_path)
        from gui.widgets.dev_boxscore_reimport_dialog import DevBoxscoreReimportDialog

        dialog = DevBoxscoreReimportDialog(
            settings_manager=self.settings_manager,
            settings=settings,
            db_path=db_path,
            parent=self,
        )
        dialog.exec()
        if dialog.result_message:
            self.boxscore_reimported.emit(dialog.result_message)

    def _current_db_path(self) -> Path | None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            return None
        return resolve_data_path(settings.db_path)

    def _refresh_database_summary(self) -> None:
        db_path = self._current_db_path()
        if db_path is None:
            self.db_summary_label.setText(tr("Select a league to view DB status."))
            self.db_path_label.setText("")
            self.reset_db_button.setEnabled(False)
            return

        summary = summarize_save_database(db_path)
        if summary.has_data:
            self.db_summary_label.setText(format_save_data_summary(summary))
        else:
            self.db_summary_label.setText(tr("No saved game, milestone, or initial stats data."))
        self.db_path_label.setText(f"DB: {db_path}")
        self.reset_db_button.setEnabled(True)

    def _reset_save_database(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league to reset first."))
            return

        db_path = resolve_data_path(settings.db_path)
        summary = summarize_save_database(db_path)
        save_name = settings.active_save or tr("Current save")
        detail = format_save_data_summary(summary) if summary.has_data else tr("No saved data")

        reply = QMessageBox.warning(
            self,
            tr("Reset Data"),
            tr(
                "All tracking data for save 「{save_name}」 will be deleted.\n\n"
                "{detail}\n\n"
                "Milestone records, season/career stats, and predictions will be permanently deleted. Continue?"
            ).format(save_name=save_name, detail=detail),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_database_reset_prepare.emit()
            reset_save_database(db_path)
        except OSError as exc:
            self.save_database_reset.emit()
            QMessageBox.critical(
                self,
                tr("Reset Failed"),
                tr("Could not delete the DB file.\n{error}").format(error=exc),
            )
            return
        except Exception as exc:
            self.save_database_reset.emit()
            QMessageBox.critical(self, tr("Reset Failed"), str(exc))
            return

        settings.import_state = {"boxscore_dir": "", "last_import_at": ""}
        self.settings = settings
        self.settings_manager.save(settings)
        self._refresh_database_summary()
        self.save_database_reset.emit()
        QMessageBox.information(
            self,
            tr("Reset Complete"),
            tr(
                "Current save data has been reset.\n"
                "Please run initial setup and import boxscores again."
            ),
        )

    def _open_korean_name_mapping(self) -> None:
        from gui.widgets.korean_name_mapping_dialog import KoreanNameMappingDialog

        dialog = KoreanNameMappingDialog(self)
        dialog.exec()
        self._refresh_korean_names_button()

    def _open_bundle_updates(self) -> None:
        from core.config.bundle_updates import apply_bundle_updates_with_message

        if apply_bundle_updates_with_message(self):
            self._on_bundle_updates_applied()

    def _on_bundle_updates_applied(self) -> None:
        self.refresh_bundle_updates_status()
        self.milestones_changed.emit()
        self.bundle_updates_changed.emit()

    def _open_milestone_definitions(self) -> None:
        from gui.widgets.milestone_definitions_dialog import MilestoneDefinitionsDialog

        path = resolve_data_path(self.settings.milestones_path)
        dialog = MilestoneDefinitionsDialog(path, self)
        dialog.definitions_changed.connect(self.milestones_changed.emit)
        dialog.exec()

    def _refresh_korean_names_button(self) -> None:
        from core.roster.korean_names import KoreanNameStore

        count = KoreanNameStore.load().pending_count()
        if self._embedded:
            self.korean_badge.setText(str(count) if count else "0")
            self.korean_badge.setVisible(bool(count))
            self.korean_names_button.setText(tr("Open Pending Mappings"))
        else:
            text = tr("Korean Name Mapping...")
            if count:
                text += f" ({count})"
            self.korean_names_button.setText(text)

    def _confirm(self) -> None:
        save_root = self.save_root_input.text().strip()
        if not save_root:
            QMessageBox.warning(self, tr("Input Required"), tr("Please select the OOTP save folder."))
            return

        if not is_valid_save_root(save_root):
            QMessageBox.warning(
                self,
                tr("Invalid Path"),
                tr("This is not an OOTP saved_games folder. Please verify the path."),
            )
            return

        index = self.league_combo.currentIndex()
        if index < 0:
            QMessageBox.warning(self, tr("League Selection Required"), tr("Please select a league."))
            return

        save_name = self.league_combo.currentText()
        save_path = str(self.league_combo.itemData(index))

        ootp_version = self._selected_version or infer_ootp_version_from_path(save_root)
        if ootp_version is None:
            ootp_version = self.settings.ootp_version

        updated = self.settings_manager.update_active_save(
            self.settings,
            save_root=save_root,
            save_name=save_name,
            save_path=save_path,
            ootp_version=ootp_version,
        )
        updated.current_season = self.season_spin.value()
        updated.season_games_total = self.season_games_spin.value()
        self.tracked_teams_widget.apply_to_settings(updated)
        new_language = self.language_combo.currentData()
        language_changed = new_language != getattr(self.settings, "language", "ko")
        updated.language = new_language
        self.settings = updated
        self.settings_manager.save(updated)
        if language_changed:
            QMessageBox.information(
                self,
                tr("Restart Required"),
                tr("Language change will take effect after restarting the app."),
            )
        self.setup_completed.emit(updated)
