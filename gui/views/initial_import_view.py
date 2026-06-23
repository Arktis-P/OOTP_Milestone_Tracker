"""Initial career stats import tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
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
        self._import_worker: InitialImportWorker | None = None
        self._pending_import: dict | None = None

        self.status_label = QLabel()
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self._update_status()

        self.batting_path = QLineEdit()
        self.pitching_path = QLineEdit()

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
        self._import_buttons = (batting_button, pitching_button, all_button)
        batting_button.clicked.connect(lambda: self._run_import("batting"))
        pitching_button.clicked.connect(lambda: self._run_import("pitching"))
        all_button.clicked.connect(lambda: self._run_import("all"))

        button_row = QHBoxLayout()
        button_row.addWidget(batting_button)
        button_row.addWidget(pitching_button)
        button_row.addWidget(all_button)
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

        main_card = CardPanel()
        main_card.content_layout.addWidget(title)
        main_card.content_layout.addWidget(subtitle)
        main_card.content_layout.addWidget(self.status_label)
        main_card.content_layout.addWidget(files_group)
        main_card.content_layout.addWidget(mode_group_box)
        main_card.content_layout.addLayout(button_row)
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

        preview = kind == "all"
        if preview:
            batting_result, pitching_result = self.importer.import_all(
                batting_path,
                pitching_path,
                mode,
                season,
                persist=False,
            )
            results = [r for r in (batting_result, pitching_result) if r]
        else:
            path = batting_path if kind == "batting" else pitching_path
            fn = self.importer.import_batting if kind == "batting" else self.importer.import_pitching
            results = [fn(path, mode, season, persist=False)]

        if not self._should_persist_after_preview(results, mode, season):
            self._update_status()
            return

        self.settings = prompt_unknown_mlb_teams(
            self,
            self.importer,
            self.settings,
            batting_path=batting_path,
            pitching_path=pitching_path,
        )
        self.settings_manager.save(self.settings)

        self._pending_import = {
            "batting_path": batting_path if kind in ("batting", "all") else None,
            "pitching_path": pitching_path if kind in ("pitching", "all") else None,
            "mode": mode,
            "season": season,
        }
        self._start_persist_worker()

    def _set_import_busy(self, busy: bool) -> None:
        for button in self._import_buttons:
            button.setEnabled(not busy)

    def _release_db_for_worker(self) -> None:
        self.aggregator.close()

    def _restore_db_after_worker(self) -> None:
        self.aggregator.reopen()
        self.importer = InitialImporter(self.aggregator)

    def _start_persist_worker(self) -> None:
        if not self._pending_import:
            return
        self._set_import_busy(True)
        self._release_db_for_worker()
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)
        payload = self._pending_import
        self._import_worker = InitialImportWorker(
            self.aggregator.db_path,
            batting_path=payload["batting_path"],
            pitching_path=payload["pitching_path"],
            mode=payload["mode"],
            current_season=payload["season"],
            persist=True,
            parent=self,
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _finish_import_worker(self) -> None:
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self._restore_db_after_worker()
        self._set_import_busy(False)

    def _on_import_progress(self, current: int, total: int, filename: str) -> None:
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)
        self.progress_label.setText(
            tr("Saving... ({current}/{total}) {filename}").format(
                current=current, total=total, filename=filename
            )
        )

    def _on_import_finished(self, _results: object) -> None:
        self._pending_import = None
        self._finish_import_worker()
        self._update_status()
        self.import_finished.emit()
        QMessageBox.information(self, tr("Done"), tr("Import completed successfully."))

    def _on_import_error(self, message: str) -> None:
        self._pending_import = None
        self._finish_import_worker()
        QMessageBox.critical(self, tr("Import Failed"), message)

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
