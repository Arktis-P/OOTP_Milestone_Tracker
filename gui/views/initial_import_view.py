"""Initial career stats import tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, SettingsManager
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.initial_import import ImportMode, InitialImporter, InitImportResult
from gui.widgets.init_compare_dialog import InitCompareDialog
from gui.widgets.mlb_team_discovery import prompt_unknown_mlb_teams
from gui.widgets.card_panel import CardPanel
from gui.workers.initial_import_worker import InitialImportWorker


class InitialImportView(QWidget):
    import_finished = pyqtSignal()

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        settings_manager: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.settings_manager = settings_manager
        self.importer = InitialImporter(aggregator)
        self._preview_worker: InitialImportWorker | None = None
        self._import_worker: InitialImportWorker | None = None
        self._pending_import: dict | None = None
        self._preview_unknown_teams: dict[str, str] = {}
        self._active_stage: str | None = None
        self._cancel_requested = False

        self.status_label = QLabel()
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        self.progress_label.setWordWrap(True)
        self.recovery_label = QLabel()
        self.recovery_label.setObjectName("warningText")
        self.recovery_label.setWordWrap(True)
        self.recovery_label.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self._update_status()

        self.batting_path = QLineEdit()
        self.pitching_path = QLineEdit()
        self.batting_path.setAccessibleName(tr("Batting export file path"))
        self.batting_path.setAccessibleDescription(
            tr("Path to player_batting_stats.txt. This value is preserved after failures for retry.")
        )
        self.pitching_path.setAccessibleName(tr("Pitching export file path"))
        self.pitching_path.setAccessibleDescription(
            tr("Path to player_pitching_stats.txt. This value is preserved after failures for retry.")
        )
        self.batting_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pitching_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.mode_first = QRadioButton(tr("Initial setup — load all data through completed season"))
        self.mode_refresh = QRadioButton(tr("Off-season update — add previous season + compare"))
        self.mode_mid = QRadioButton(tr("Mid-season compare — check differences without saving"))
        self.mode_first.setChecked(True)
        if self.importer.is_init_empty():
            self.mode_first.setChecked(True)
        else:
            self.mode_refresh.setChecked(True)

        mode_group = QButtonGroup(self)
        for button in (self.mode_first, self.mode_refresh, self.mode_mid):
            mode_group.addButton(button)

        batting_button = QPushButton(tr("Batting"))
        pitching_button = QPushButton(tr("Pitching"))
        all_button = QPushButton(tr("📥  Load Database"))
        all_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setAccessibleName(tr("Cancel current initial import"))
        self.cancel_button.setToolTip(
            tr("Cancels after the current file finishes; the file currently being parsed cannot be interrupted immediately.")
        )
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_operation)
        self.retry_button = QPushButton(tr("Retry"))
        self.retry_button.setObjectName("secondaryButton")
        self.retry_button.setAccessibleName(tr("Retry previous initial import"))
        self.retry_button.setToolTip(
            tr("Runs the previous initial import again with the same files and mode.")
        )
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self._retry_pending_import)
        self._import_buttons = (batting_button, pitching_button, all_button)
        batting_button.clicked.connect(lambda: self._run_import("batting"))
        pitching_button.clicked.connect(lambda: self._run_import("pitching"))
        all_button.clicked.connect(lambda: self._run_import("all"))
        batting_button.setAccessibleName(tr("Load batting baseline stats"))
        pitching_button.setAccessibleName(tr("Load pitching baseline stats"))
        all_button.setAccessibleName(tr("Load batting and pitching baseline stats"))
        self.cancel_button.setAccessibleName(tr("Cancel current import step"))
        self.retry_button.setAccessibleName(tr("Retry the last import attempt"))

        button_row = QHBoxLayout()
        button_row.addWidget(batting_button)
        button_row.addWidget(pitching_button)
        button_row.addWidget(all_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.retry_button)
        button_row.addStretch()

        files_group = QGroupBox(tr("File Selection"))
        files_layout = QVBoxLayout(files_group)
        files_layout.addLayout(
            self._path_row(tr("Batting"), self.batting_path, "player_batting_stats.txt")
        )
        files_layout.addLayout(
            self._path_row(tr("Pitching"), self.pitching_path, "player_pitching_stats.txt")
        )

        mode_group_box = QGroupBox(tr("Import Mode"))
        mode_layout = QVBoxLayout(mode_group_box)
        mode_layout.addWidget(self.mode_first)
        mode_layout.addWidget(self.mode_refresh)
        mode_layout.addWidget(self.mode_mid)

        title = QLabel(tr("Register Historical Career & Season Baseline Stats"))
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            tr(
                "Loads career baseline data from player_batting_stats.txt · "
                "player_pitching_stats.txt exported from OOTP."
            )
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setWordWrap(True)

        main_card = CardPanel()
        main_card.content_layout.addWidget(title)
        main_card.content_layout.addWidget(subtitle)
        main_card.content_layout.addWidget(self.status_label)
        main_card.content_layout.addWidget(files_group)
        main_card.content_layout.addWidget(mode_group_box)
        main_card.content_layout.addLayout(button_row)
        main_card.content_layout.addWidget(self.recovery_label)
        main_card.content_layout.addWidget(self.progress_label)
        main_card.content_layout.addWidget(self.progress_bar)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_card, stretch=1)

        self._prefill_paths()

    def _stats_directory(self) -> Path | None:
        directory = self.settings.import_export_dir or self.settings.initial_stats_dir
        if not directory:
            return None
        return Path(directory)

    def _prefill_paths(self) -> None:
        base = self._stats_directory()
        if base is None:
            return
        self.batting_path.setText(str(base / "player_batting_stats.txt"))
        self.pitching_path.setText(str(base / "player_pitching_stats.txt"))

    def _path_row(self, label: str, field: QLineEdit, default_name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        browse = QPushButton(tr("Browse"))

        def pick() -> None:
            start = (
                field.text()
                or self.settings.import_export_dir
                or self.settings.initial_stats_dir
                or str(Path.home())
            )
            selected, _ = QFileDialog.getOpenFileName(
                self,
                tr("Select {filename}").format(filename=default_name),
                start,
                "Text files (*.txt);;All files (*)",
            )
            if selected:
                field.setText(selected)
                self.settings.initial_stats_dir = str(Path(selected).parent)
                self.settings_manager.save(self.settings)

        browse.clicked.connect(pick)
        row.addWidget(QLabel(label))
        row.addWidget(field, stretch=1)
        row.addWidget(browse)
        return row

    def _selected_mode(self) -> ImportMode:
        if self.mode_refresh.isChecked():
            return "refresh"
        if self.mode_mid.isChecked():
            return "mid_season"
        return "first_time"

    def _run_import(self, kind: str) -> None:
        if self._active_stage is not None:
            QMessageBox.information(
                self,
                tr("Import In Progress"),
                tr("The current import step is still running. Please wait for it to finish."),
            )
            return

        mode = self._selected_mode()
        season = self.settings.current_season

        if mode == "mid_season":
            reply = QMessageBox.warning(
                self,
                tr("Mid-season Import"),
                tr(
                    "Data for the current season ({season}) will not be saved to the DB.\n"
                    "Only a comparison with boxscore totals will be run.\n\nContinue?"
                ).format(season=season),
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        batting_path = self.batting_path.text().strip() or None
        pitching_path = self.pitching_path.text().strip() or None
        if kind == "batting" and not batting_path:
            QMessageBox.warning(self, tr("File Required"), tr("Please select a batting file."))
            return
        if kind == "pitching" and not pitching_path:
            QMessageBox.warning(self, tr("File Required"), tr("Please select a pitching file."))
            return
        if kind == "all" and not batting_path and not pitching_path:
            QMessageBox.warning(self, tr("File Required"), tr("Please select a batting or pitching file."))
            return

        selected_batting = batting_path if kind in ("batting", "all") else None
        selected_pitching = pitching_path if kind in ("pitching", "all") else None
        if not self._validate_paths(selected_batting, selected_pitching):
            return

        self._pending_import = {
            "batting_path": selected_batting,
            "pitching_path": selected_pitching,
            "mode": mode,
            "season": season,
        }
        self._clear_recovery_message()
        self._start_preview_worker()

    def _validate_paths(
        self, batting_path: str | None, pitching_path: str | None
    ) -> bool:
        for label, raw_path in (
            (tr("Batting"), batting_path),
            (tr("Pitching"), pitching_path),
        ):
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                if not path.is_file():
                    raise FileNotFoundError
                if path.stat().st_size == 0:
                    QMessageBox.warning(
                        self,
                        tr("Empty Export File"),
                        tr("The {kind} export is empty. Export it again from OOTP and retry.\n\n{path}").format(
                            kind=label, path=path
                        ),
                    )
                    return False
            except OSError:
                QMessageBox.warning(
                    self,
                    tr("File Not Available"),
                    tr("The {kind} export cannot be read. Check the path and permissions, then retry.\n\n{path}").format(
                        kind=label, path=path
                    ),
                )
                return False
        return True

    def _set_import_busy(self, busy: bool) -> None:
        for button in self._import_buttons:
            button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy and not self._cancel_requested)
        if busy:
            self.retry_button.setVisible(False)

    def _set_retry_available(self, available: bool) -> None:
        self.retry_button.setVisible(available and self._pending_import is not None)
        self.retry_button.setEnabled(available and self._pending_import is not None)

    def _show_recovery_message(self, message: str) -> None:
        self.recovery_label.setText(tr("Action: {message}").format(message=message))
        self.recovery_label.setVisible(True)

    def _clear_recovery_message(self) -> None:
        self.recovery_label.clear()
        self.recovery_label.setVisible(False)

    def has_active_operation(self) -> bool:
        """Return whether this view currently owns a running import operation."""
        if self._active_stage is not None:
            return True
        return any(
            worker is not None and worker.isRunning()
            for worker in (self._preview_worker, self._import_worker)
        )

    def _release_db_for_worker(self) -> None:
        self.aggregator.close()

    def _restore_db_after_worker(self) -> None:
        self.aggregator.reopen()
        self.importer = InitialImporter(self.aggregator)

    def _start_preview_worker(self) -> None:
        if not self._pending_import or self._active_stage is not None:
            return
        payload = self._pending_import
        self._active_stage = "preview"
        self._cancel_requested = False
        self._preview_unknown_teams = {}
        self._set_import_busy(True)
        self._set_retry_available(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText(
            tr("Analyzing export files... Keep this window open until the step finishes.")
        )
        self.progress_label.setVisible(True)
        worker = InitialImportWorker(
            self.aggregator.db_path,
            batting_path=payload["batting_path"],
            pitching_path=payload["pitching_path"],
            mode=payload["mode"],
            current_season=payload["season"],
            persist=False,
            known_teams=self.settings.team_name_map(),
            parent=self,
        )
        self._preview_worker = worker
        worker.progress.connect(self._on_import_progress)
        worker.discovered_teams.connect(self._on_teams_discovered)
        worker.completed.connect(self._on_preview_finished)
        worker.error.connect(self._on_preview_error)
        worker.cancelled.connect(self._on_preview_cancelled)
        worker.finished.connect(lambda: self._on_thread_stopped(worker))
        worker.start()

    def _on_teams_discovered(self, teams: object) -> None:
        self._preview_unknown_teams = dict(teams) if isinstance(teams, dict) else {}

    def _on_preview_finished(self, results: object) -> None:
        if self._active_stage != "preview" or not self._pending_import:
            return
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        result_list = list(results) if isinstance(results, list) else []
        payload = self._pending_import
        if not self._should_persist_after_preview(
            result_list, payload["mode"], payload["season"]
        ):
            self._reset_operation()
            self._update_status()
            return

        self.settings = prompt_unknown_mlb_teams(
            self,
            self.importer,
            self.settings,
            batting_path=payload["batting_path"],
            pitching_path=payload["pitching_path"],
            discovered_teams=self._preview_unknown_teams,
        )
        self.settings_manager.save(self.settings)
        self._active_stage = None
        self._start_persist_worker()

    def _on_preview_error(self, message: str) -> None:
        self._reset_operation(preserve_pending=True)
        self._set_retry_available(True)
        self._show_recovery_message(
            tr("Preview failed. No live data was changed. Check the export file and retry with the same paths.")
        )
        QMessageBox.critical(
            self,
            tr("Preview Failed"),
            tr("The export could not be analyzed. No data was changed.\n\n{error}\n\nCheck the selected file and retry.").format(
                error=message
            ),
        )

    def _on_preview_cancelled(self, message: str, _results: object) -> None:
        self._reset_operation(preserve_pending=True)
        self._set_retry_available(True)
        self._show_recovery_message(
            tr("Preview cancelled after the current file finished. No live data was changed.")
        )
        self.progress_label.setText(
            tr("Preview cancelled. No data was changed. You can retry with the same files and mode.")
        )
        self.progress_label.setVisible(True)

    def _start_persist_worker(self) -> None:
        if not self._pending_import or self._active_stage is not None:
            return
        self._active_stage = "import"
        self._cancel_requested = False
        self._set_import_busy(True)
        self._set_retry_available(False)
        self._release_db_for_worker()
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(
            tr("Saving import... Keep this window open until the step finishes.")
        )
        payload = self._pending_import
        worker = InitialImportWorker(
            self.aggregator.db_path,
            batting_path=payload["batting_path"],
            pitching_path=payload["pitching_path"],
            mode=payload["mode"],
            current_season=payload["season"],
            persist=True,
            parent=self,
        )
        self._import_worker = worker
        worker.progress.connect(self._on_import_progress)
        worker.completed.connect(self._on_import_finished)
        worker.error.connect(self._on_import_error)
        worker.cancelled.connect(self._on_import_cancelled)
        worker.finished.connect(lambda: self._on_thread_stopped(worker))
        worker.start()

    def _finish_import_worker(self) -> None:
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self._restore_db_after_worker()
        self._active_stage = None
        self._cancel_requested = False
        self._set_import_busy(False)

    def _on_import_progress(self, current: int, total: int, filename: str) -> None:
        stage = tr("Analyzing") if self._active_stage == "preview" else tr("Saving")
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)
        self.progress_label.setText(
            tr("{stage}... ({current}/{total}) {filename} — keep this window open").format(
                stage=stage, current=current, total=total, filename=filename
            )
        )

    def _on_import_finished(self, _results: object) -> None:
        results = list(_results) if isinstance(_results, list) else []
        failures: list[str] = []
        if not results:
            failures.append(tr("No import result was returned."))
        for result in results:
            kind = tr("Batting") if result.kind == "batting" else tr("Pitching")
            if result.errors:
                failures.extend(f"{kind}: {error}" for error in result.errors[:8])
            if result.total_scanned == 0:
                failures.append(tr("{kind}: no player records were found.").format(kind=kind))
            if not result.saved:
                failures.append(tr("{kind}: no data was saved.").format(kind=kind))

        self._finish_import_worker()
        self._update_status()
        if failures:
            self._set_retry_available(True)
            self._show_recovery_message(
                tr("Import was incomplete. Some selected files may already be saved; review status or restore a backup before retrying.")
            )
            QMessageBox.critical(
                self,
                tr("Import Incomplete"),
                tr(
                    "The import did not complete for every selected file. Some data may already have been saved; no completion notification was sent.\n\n"
                    "{details}\n\nReview the import status or restore a backup if needed, correct the export, and retry."
                ).format(details="\n".join(failures)),
            )
            return
        self._pending_import = None
        self._set_retry_available(False)
        self._clear_recovery_message()
        self.import_finished.emit()
        QMessageBox.information(self, tr("Done"), tr("Import completed successfully."))

    def _on_import_error(self, message: str) -> None:
        self._finish_import_worker()
        self._set_retry_available(True)
        self._show_recovery_message(
            tr("Import failed after saving started. Data from an earlier file may already be saved.")
        )
        QMessageBox.critical(
            self,
            tr("Import Failed"),
            tr("The import could not be completed. The database connection was restored, but data from an earlier file may already have been saved.\n\n{error}\n\nReview the import status or restore a backup if needed, then retry.").format(
                error=message
            ),
        )

    def _on_import_cancelled(self, message: str, results: object) -> None:
        completed = len(results) if isinstance(results, list) else 0
        self._finish_import_worker()
        self._update_status()
        self._set_retry_available(True)
        self._show_recovery_message(
            tr("Import cancelled after the current file finished. A completed earlier file may already be saved.")
        )
        self.progress_label.setText(
            tr("Import cancelled after the current file finished. {completed} file(s) may already have been saved; review status or restore a backup before retrying.").format(
                completed=completed
            )
        )
        self.progress_label.setVisible(True)

    def _cancel_operation(self) -> None:
        if self._active_stage is None:
            return
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.progress_label.setText(
            tr("Cancelling after the current file finishes. The file currently being parsed cannot be interrupted immediately.")
        )
        self.progress_label.setVisible(True)
        worker = self._preview_worker if self._active_stage == "preview" else self._import_worker
        if worker is not None:
            worker.cancel()

    def _retry_pending_import(self) -> None:
        if self._active_stage is not None or not self._pending_import:
            return
        self._set_retry_available(False)
        self._start_preview_worker()

    def _reset_operation(self, *, preserve_pending: bool = False) -> None:
        if not preserve_pending:
            self._pending_import = None
        self._active_stage = None
        self._cancel_requested = False
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self._set_import_busy(False)

    def _on_thread_stopped(self, worker: InitialImportWorker) -> None:
        if self._preview_worker is worker:
            self._preview_worker = None
        if self._import_worker is worker:
            self._import_worker = None
        worker.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.has_active_operation():
            QMessageBox.information(
                self,
                tr("Import In Progress"),
                tr("This window must remain open until the current import step finishes."),
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _should_persist_after_preview(
        self, results: list[InitImportResult], mode: ImportMode, season: int
    ) -> bool:
        all_diffs: list = []
        for result in results:
            if result.errors:
                QMessageBox.warning(
                    self,
                    tr("Error"),
                    "\n".join(result.errors[:8]),
                )
                return False
            if result.total_scanned == 0:
                QMessageBox.warning(
                    self,
                    tr("No Player Records Found"),
                    tr("No player records were found in the export. No data was changed. Export the file again from OOTP and retry."),
                )
                return False
            all_diffs.extend(result.diffs)

        if mode == "refresh" and all_diffs:
            dialog = InitCompareDialog(
                tr("Off-season update — {prev_season} season comparison results").format(
                    prev_season=season - 1
                ),
                all_diffs,
                allow_save=True,
                parent=self,
            )
            dialog.exec()
            return dialog.save_confirmed

        if mode == "mid_season":
            dialog = InitCompareDialog(
                tr("Mid-season compare — {season} season (not saved)").format(season=season),
                [d for d in all_diffs if d.season == season],
                allow_save=False,
                parent=self,
            )
            dialog.exec()
            gap_diffs = [d for d in all_diffs if d.season < season]
            if gap_diffs:
                gap_dialog = InitCompareDialog(
                    tr("Previous season update comparison"),
                    gap_diffs,
                    allow_save=True,
                    save_label=tr("Add based on file"),
                    parent=self,
                )
                gap_dialog.exec()
                return gap_dialog.save_confirmed
            return False

        if mode == "refresh" and not all_diffs:
            reply = QMessageBox.question(
                self,
                tr("Comparison Result"),
                tr(
                    "{prev_season} season: no differences between boxscores and file values.\n"
                    "Update based on file?"
                ).format(prev_season=season - 1),
            )
            return reply == QMessageBox.StandardButton.Yes

        return True

    def _update_status(self) -> None:
        summary = self.importer.get_init_summary()
        batting_at = summary["batting_imported_at"][:10] if summary["batting_imported_at"] else "-"
        pitching_at = summary["pitching_imported_at"][:10] if summary["pitching_imported_at"] else "-"
        coverage = summary["season_coverage"]
        self.status_label.setText(
            tr(
                "Batting: {batting_players:,} players · through {coverage} season (updated {batting_at})\n"
                "Pitching: {pitching_players:,} players · through {coverage} season (updated {pitching_at})"
            ).format(
                batting_players=summary["batting_players"],
                pitching_players=summary["pitching_players"],
                coverage=coverage,
                batting_at=batting_at,
                pitching_at=pitching_at,
            )
        )
