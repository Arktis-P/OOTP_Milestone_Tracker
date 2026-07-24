"""Advanced and risky maintenance tools separated from normal settings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, SettingsManager, resolve_data_path
from core.db.reset import (
    format_save_data_summary,
    reset_save_database,
    summarize_save_database,
)
from core.i18n import tr
from gui.theme import TEXT_MUTED
from gui.widgets.card_panel import CardPanel, tool_row


class AdvancedToolsView(QWidget):
    """Maintenance page for recovery, developer, and destructive tools."""

    save_database_reset_prepare = pyqtSignal()
    save_database_reset = pyqtSignal()
    boxscore_reimported = pyqtSignal(str)

    def __init__(
        self,
        settings_manager: SettingsManager,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.settings = settings
        self._recovery_worker = None
        self._season_validation_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel(tr("Advanced Tools"))
        title.setObjectName("pageTitle")
        intro = QLabel(
            tr(
                "Use these tools only for recovery, one-off repairs, or destructive maintenance. "
                "Normal OOTP connection and display settings are kept on the Settings page."
            )
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedLabel")
        layout.addWidget(title)
        layout.addWidget(intro)

        self.dev_reimport_button = QPushButton(tr("Re-import Individual Boxscores"))
        self.dev_reimport_button.clicked.connect(self._open_dev_boxscore_reimport)
        self.purge_spring_training_button = QPushButton(tr("Remove Spring Training Games"))
        self.purge_spring_training_button.clicked.connect(self._purge_spring_training_games)
        self.recover_regular_season_button = QPushButton(tr("Recover Regular Season Games"))
        self.recover_regular_season_button.clicked.connect(self._recover_regular_season_games)
        self.season_validation_button = QPushButton(tr("Run Season Isolation Validation"))
        self.season_validation_button.clicked.connect(self._run_season_validation)

        maintenance_card = CardPanel(tr("Maintenance and recovery"))
        maintenance_card.add_widget(
            tool_row(
                tr("Individual boxscore re-import"),
                tr("Re-run a selected boxscore when a single source file needs repair."),
                self.dev_reimport_button,
            )
        )
        maintenance_card.add_widget(
            tool_row(
                tr("Spring training cleanup"),
                tr("Remove spring training games from tracked data without presenting it as normal import."),
                self.purge_spring_training_button,
            )
        )
        maintenance_card.add_widget(
            tool_row(
                tr("Regular season recovery"),
                tr("Scan for regular season games that may have been skipped after cleanup."),
                self.recover_regular_season_button,
            )
        )
        maintenance_card.add_widget(
            tool_row(
                tr("Season isolation validation"),
                tr(
                    "Replay the season into a separate validation DB and report differences. "
                    "This does not write to the operating app DB."
                ),
                self.season_validation_button,
            )
        )
        self.validation_status_label = QLabel(
            tr("Validation target: separate validation DB only. Operating DB is not modified.")
        )
        self.validation_status_label.setWordWrap(True)
        self.validation_status_label.setObjectName("mutedLabel")
        self.validation_report_label = QLabel("")
        self.validation_report_label.setWordWrap(True)
        self.validation_report_label.setObjectName("mutedLabel")
        maintenance_card.add_widget(self.validation_status_label)
        maintenance_card.add_widget(self.validation_report_label)
        layout.addWidget(maintenance_card)

        self.db_summary_label = QLabel()
        self.db_summary_label.setWordWrap(True)
        self.db_summary_label.setObjectName("mutedLabel")
        self.db_path_label = QLabel()
        self.db_path_label.setWordWrap(True)
        self.db_path_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.refresh_db_summary_button = QPushButton(tr("Refresh Status"))
        self.refresh_db_summary_button.clicked.connect(self.refresh_database_summary)
        self.reset_db_button = QPushButton(tr("Full DB Reset"))
        self.reset_db_button.setObjectName("dangerButton")
        self.reset_db_button.clicked.connect(self._reset_save_database)

        danger_card = CardPanel(tr("Danger zone"))
        warning = QLabel(
            tr(
                "Full DB reset deletes milestone records, imported games, initial stats, "
                "predictions, and processed-source history for the selected save. Back up "
                "the save and app data before continuing."
            )
        )
        warning.setWordWrap(True)
        warning.setObjectName("errorLabel")
        danger_card.add_widget(warning)
        danger_card.add_widget(self.db_summary_label)
        danger_card.add_widget(self.db_path_label)
        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_db_summary_button)
        buttons.addStretch()
        buttons.addWidget(self.reset_db_button)
        danger_card.add_layout(buttons)
        layout.addWidget(danger_card)
        layout.addStretch()
        self.refresh_database_summary()

    def set_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.refresh_database_summary()

    def _build_season_validation_config(self):
        from core.validation.season_replay import build_config_from_settings

        settings = self.settings_manager.ensure_derived_paths(self.settings)
        return build_config_from_settings(
            save_path=settings.active_save_path,
            season=settings.current_season,
            tracked_teams=list(settings.tracked_teams),
            mlb_only=settings.import_mlb_only,
            boxscore_dir=settings.boxscore_dir,
            milestones_path=resolve_data_path(settings.milestones_path),
            reset=True,
            dry_run=False,
        )

    def _current_db_path(self) -> Path | None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            return None
        return resolve_data_path(settings.db_path)

    def refresh_database_summary(self) -> None:
        db_path = self._current_db_path()
        if db_path is None:
            self.db_summary_label.setText(tr("Select a league to view DB status."))
            self.db_path_label.setText("")
            self.reset_db_button.setEnabled(False)
            return
        summary = summarize_save_database(db_path)
        self.db_summary_label.setText(
            format_save_data_summary(summary)
            if summary.has_data
            else tr("No saved game, milestone, or initial stats data.")
        )
        self.db_path_label.setText(f"DB: {db_path}")
        self.reset_db_button.setEnabled(True)

    def _open_dev_boxscore_reimport(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league to re-import first."))
            return
        from gui.widgets.dev_boxscore_reimport_dialog import DevBoxscoreReimportDialog

        dialog = DevBoxscoreReimportDialog(
            settings_manager=self.settings_manager,
            settings=settings,
            db_path=resolve_data_path(settings.db_path),
            parent=self,
        )
        dialog.exec()
        if dialog.result_message:
            self.boxscore_reimported.emit(dialog.result_message)

    def _purge_spring_training_games(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league first."))
            return
        if not settings.boxscore_dir:
            QMessageBox.warning(self, tr("Path Required"), tr("Box score folder is not set."))
            return
        from core.stats.aggregator import Aggregator

        with Aggregator(resolve_data_path(settings.db_path)) as aggregator:
            removed = aggregator.purge_spring_training_games(settings.boxscore_dir)
        self.refresh_database_summary()
        self.boxscore_reimported.emit(
            tr("Removed {count} spring training games.").format(count=len(removed))
        )

    def _recover_regular_season_games(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league first."))
            return
        if not settings.boxscore_dir:
            QMessageBox.warning(self, tr("Path Required"), tr("Box score folder is not set."))
            return
        from gui.workers.recovery_worker import RecoverRegularSeasonWorker

        self.recover_regular_season_button.setEnabled(False)
        self.recover_regular_season_button.setText(tr("Scanning..."))
        worker = RecoverRegularSeasonWorker(
            resolve_data_path(settings.db_path),
            settings.boxscore_dir,
            settings.current_season,
            self,
        )
        worker.finished.connect(self._on_recover_regular_season_finished)
        worker.error.connect(self._on_recover_regular_season_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._recovery_worker = worker
        worker.start()

    def _on_recover_regular_season_finished(self, report: dict) -> None:
        self.recover_regular_season_button.setEnabled(True)
        self.recover_regular_season_button.setText(tr("Recover Regular Season Games"))
        self._recovery_worker = None
        self.refresh_database_summary()
        imported = report.get("imported_game_ids") or []
        self.boxscore_reimported.emit(
            tr("Recovered {count} regular season games.").format(count=len(imported))
        )

    def _on_recover_regular_season_error(self, message: str) -> None:
        self.recover_regular_season_button.setEnabled(True)
        self.recover_regular_season_button.setText(tr("Recover Regular Season Games"))
        self._recovery_worker = None
        QMessageBox.warning(self, tr("Recovery Failed"), message)

    def _run_season_validation(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league first."))
            return
        try:
            config = self._build_season_validation_config()
        except Exception as exc:
            self.validation_status_label.setText(
                tr("Validation could not start: {error}").format(error=exc)
            )
            return
        self.season_validation_button.setEnabled(False)
        self.season_validation_button.setText(tr("Validation running..."))
        self.validation_status_label.setText(
            tr(
                "Running validation-only replay for season {season}.\n"
                "Target DB: {target}\n"
                "Live DB: {live}\n"
                "The live DB will not be modified."
            ).format(season=config.season, target=config.target_db, live=config.live_db)
        )
        self.validation_report_label.setText("")
        from gui.workers.season_validation_worker import SeasonValidationWorker

        worker = SeasonValidationWorker(config, self)
        worker.completed.connect(self._on_season_validation_finished)
        worker.error.connect(self._on_season_validation_error)
        worker.finished.connect(worker.deleteLater)
        self._season_validation_worker = worker
        worker.start()

    def _on_season_validation_finished(self, report: dict, report_path: str) -> None:
        self.season_validation_button.setEnabled(True)
        self.season_validation_button.setText(tr("Run Season Isolation Validation"))
        self._season_validation_worker = None
        db_summary = report.get("db_summary") or {}
        boxscores = report.get("boxscores") or {}
        messages = report.get("messages") or {}
        self.validation_status_label.setText(
            tr("Validation replay completed. Operating DB was not modified.")
        )
        self.validation_report_label.setText(
            tr(
                "Report: {report_path}\n"
                "Validation DB records: {records}\n"
                "Boxscores checked: {boxscores}\n"
                "Messages checked: {messages}\n"
                "Review this report before deciding whether any separate repair is needed."
            ).format(
                report_path=report_path,
                records=db_summary.get("milestone_records", 0),
                boxscores=boxscores.get("source_total", 0),
                messages=messages.get("source_total", 0),
            )
        )

    def _on_season_validation_error(self, message: str) -> None:
        self.season_validation_button.setEnabled(True)
        self.season_validation_button.setText(tr("Run Season Isolation Validation"))
        self._season_validation_worker = None
        self.validation_status_label.setText(
            tr("Validation failed. Operating DB was not modified.")
        )
        self.validation_report_label.setText(message)

    def _reset_save_database(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, tr("League Required"), tr("Please select a league to reset first."))
            return
        save_name = settings.active_save or tr("Current save")
        typed, ok = QInputDialog.getText(
            self,
            tr("Confirm Full DB Reset"),
            tr("Type the save name exactly to reset its app database:\n{save_name}").format(
                save_name=save_name
            ),
        )
        if not ok or typed.strip() != save_name:
            QMessageBox.information(self, tr("Reset Cancelled"), tr("Save name did not match. Nothing was deleted."))
            return
        db_path = resolve_data_path(settings.db_path)
        summary = summarize_save_database(db_path)
        detail = format_save_data_summary(summary) if summary.has_data else tr("No saved data")
        reply = QMessageBox.warning(
            self,
            tr("Reset Data"),
            tr(
                "Problem: this permanently deletes app tracking data for 「{save_name}」.\n"
                "Impact: milestone records, imported games, initial stats, predictions, and processed-source history are removed.\n"
                "Backup: copy the save and app data before continuing.\n\n"
                "Delete target summary:\n{detail}\n\nContinue?"
            ).format(save_name=save_name, detail=detail),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.save_database_reset_prepare.emit()
            reset_save_database(db_path)
        except Exception as exc:
            self.save_database_reset.emit()
            QMessageBox.critical(self, tr("Reset Failed"), str(exc))
            return
        settings.import_state = {"boxscore_dir": "", "last_import_at": ""}
        self.settings = settings
        self.settings_manager.save(settings)
        self.refresh_database_summary()
        self.save_database_reset.emit()
        QMessageBox.information(self, tr("Reset Complete"), tr("Current save data has been reset."))
