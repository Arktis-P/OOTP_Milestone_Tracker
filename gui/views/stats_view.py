"""Player statistics tab with tracked-team filter."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.config.settings_manager import SettingsManager
from core.i18n import tr
from core.db.meta import get_init_season_coverage
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import outs_to_ip_str
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_roster_player_names,
)
from core.stats.player_display import (
    best_display_name,
    format_player_header,
    format_player_list_label,
)
from core.stats.position_filter import (
    POSITION_FILTER_OPTIONS,
    player_matches_position_group,
)
from gui.widgets.error_banner import ErrorBanner
from gui.widgets.milestone_dialog import MilestoneAchievedDialog
from gui.widgets.player_game_log_dialog import PlayerGameLogDialog
from gui.widgets.player_milestone_timeline import PlayerMilestoneTimeline
from gui.widgets.table_widgets import SortableTable
from gui.theme import TEXT_SECONDARY, header_panel_style, hint_style
from gui.widgets.card_panel import CardPanel, section_label
from gui.workers.import_worker import ImportFinishedPayload, ImportWorker


class StatsView(QWidget):
    import_finished = pyqtSignal(str)

    BATTING_COLUMNS = [
        "G", "AB", "H", "2B", "3B", "HR", "RBI", "R", "BB", "K", "SB", "AVG", "OBP", "SLG", "OPS"
    ]
    PITCHING_COLUMNS = [
        "G", "GS", "W", "L", "SV", "IP", "K", "BB", "HR", "ERA", "WHIP", "CG", "SHO"
    ]

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        milestones: MilestoneDefinitions,
        settings_manager: SettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.milestones = milestones
        self.settings_manager = settings_manager or SettingsManager()
        self._import_worker: ImportWorker | None = None
        self._players: list[dict] = []
        self._players_by_id: dict[int, dict] = {}
        self._career_mode = False

        self.banner = ErrorBanner(self)
        self.import_button = QPushButton(tr("📥  Import Boxscores"))
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self.start_import)
        self.mlb_only_checkbox = QCheckBox(tr("MLB Only"))
        self.mlb_only_checkbox.setChecked(self.settings.import_mlb_only)
        self.mlb_only_checkbox.setToolTip(
            tr("Imports Major League boxscores only. KBO, WBC, etc. are skipped.")
        )
        self.mlb_only_checkbox.toggled.connect(self._on_mlb_only_toggled)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet(hint_style(TEXT_SECONDARY))
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        self.career_toggle = QPushButton(tr("View Career Records"))
        self.career_toggle.setCheckable(True)
        self.career_toggle.toggled.connect(self._on_career_toggled)

        mode_wrap = QWidget()
        mode_layout = QHBoxLayout(mode_wrap)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(0)
        self.mode_season_btn = QPushButton(tr("Season"))
        self.mode_career_btn = QPushButton(tr("Career"))
        for btn in (self.mode_season_btn, self.mode_career_btn):
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setObjectName("modeBtn")
        self.mode_season_btn.setChecked(True)
        self.mode_season_btn.clicked.connect(lambda: self._set_mode_buttons("season"))
        self.mode_career_btn.clicked.connect(lambda: self._set_mode_buttons("career"))
        mode_layout.addWidget(self.mode_season_btn)
        mode_layout.addWidget(self.mode_career_btn)
        self.career_toggle.hide()

        self.season_combo = QComboBox()
        self.season_combo.currentIndexChanged.connect(self._on_season_changed)

        self.position_combo = QComboBox()
        for label, value in POSITION_FILTER_OPTIONS:
            self.position_combo.addItem(label, value)
        self.position_combo.currentIndexChanged.connect(self._apply_player_filter)

        self.player_search = QLineEdit()
        self.player_search.setPlaceholderText(tr("Search player..."))
        self.player_search.setClearButtonEnabled(True)
        self.player_search.setToolTip(
            tr("Filter list by name or ID. Does not re-query DB on each input.")
        )
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_player_filter)

        self.player_list = QListWidget()
        self.player_list.currentRowChanged.connect(self._on_list_selection)

        self.player_header = QLabel()
        self.player_header.setWordWrap(True)
        self.player_header.setTextFormat(Qt.TextFormat.RichText)
        self.player_header.setStyleSheet(header_panel_style())

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)

        self.batting_table = SortableTable([tr("Stat")] + self.BATTING_COLUMNS)
        self.pitching_table = SortableTable([tr("Stat")] + self.PITCHING_COLUMNS)
        self.batting_table.cellDoubleClicked.connect(self._open_game_logs)
        self.pitching_table.cellDoubleClicked.connect(self._open_game_logs)

        self.milestone_timeline = PlayerMilestoneTimeline(
            self.aggregator, self.milestones, self.settings
        )

        self.stats_tabs = QTabWidget()
        batting_page = QWidget()
        batting_layout = QVBoxLayout(batting_page)
        batting_layout.setContentsMargins(4, 4, 4, 4)
        batting_layout.addWidget(self.batting_table)
        pitching_page = QWidget()
        pitching_layout = QVBoxLayout(pitching_page)
        pitching_layout.setContentsMargins(4, 4, 4, 4)
        pitching_layout.addWidget(self.pitching_table)
        self.stats_tabs.addTab(batting_page, tr("Batting"))
        self.stats_tabs.addTab(pitching_page, tr("Pitching"))
        self.stats_tabs.addTab(self.milestone_timeline, tr("Milestones"))

        import_row = QHBoxLayout()
        import_row.addWidget(self.import_button)
        import_row.addWidget(self.mlb_only_checkbox)
        import_row.addWidget(self.progress_label)
        import_row.addWidget(self.progress_bar, stretch=1)
        import_row.addStretch()
        import_row.addWidget(mode_wrap)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(section_label(tr("Season")))
        filter_row.addWidget(self.season_combo)
        filter_row.addWidget(section_label(tr("Position")))
        filter_row.addWidget(self.position_combo)
        filter_row.addWidget(self.player_search, stretch=1)

        toolbar_card = CardPanel()
        toolbar_card.content_layout.addLayout(import_row)
        toolbar_card.content_layout.addLayout(filter_row)

        list_card = CardPanel(tr("Tracked Players"))
        list_card.add_widget(self.player_list)

        detail_card = CardPanel()
        detail_card.content_layout.addWidget(self.player_header)
        detail_card.content_layout.addWidget(self.info_label)
        detail_card.content_layout.addWidget(self.stats_tabs, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_card)
        splitter.addWidget(detail_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 560])

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.banner)
        layout.addWidget(toolbar_card)
        layout.addWidget(splitter, stretch=1)

        self.player_search.textChanged.connect(self._on_search_text_changed)
        self._reload_seasons()
        self.reload_players()

    def _set_mode_buttons(self, mode: str) -> None:
        career = mode == "career"
        self.mode_season_btn.setChecked(not career)
        self.mode_career_btn.setChecked(career)
        if self.career_toggle.isChecked() != career:
            self.career_toggle.blockSignals(True)
            self.career_toggle.setChecked(career)
            self.career_toggle.blockSignals(False)
        self._on_career_toggled(career)

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _on_career_toggled(self, checked: bool) -> None:
        self._career_mode = checked
        self.mode_season_btn.setChecked(not checked)
        self.mode_career_btn.setChecked(checked)
        self.season_combo.setEnabled(not checked)
        self._refresh_player_stats()

    def _on_season_changed(self) -> None:
        if self.season_combo.currentData() == "career":
            self.career_toggle.setChecked(True)
        else:
            self.career_toggle.setChecked(False)
        self._refresh_player_stats()

    def _reload_seasons(self) -> None:
        self.season_combo.blockSignals(True)
        self.season_combo.clear()
        for season in self.aggregator.get_available_seasons():
            self.season_combo.addItem(str(season), season)
        if self.settings.current_season not in self.aggregator.get_available_seasons():
            self.season_combo.insertItem(0, str(self.settings.current_season), self.settings.current_season)
        index = self.season_combo.findData(self.settings.current_season)
        if index >= 0:
            self.season_combo.setCurrentIndex(index)
        self.season_combo.addItem(tr("Career"), "career")
        self.season_combo.blockSignals(False)

    def on_data_refreshed(self, kind: str) -> None:
        if kind in ("boxscore", "init", "all"):
            if kind in ("boxscore", "all"):
                self._reload_seasons()
            self.reload_players()

    def reload_players(self) -> None:
        """Load player list from DB once (after import or settings change)."""
        self._players = self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        self._players_by_id = {int(p["player_id"]): p for p in self._players}
        if not self._players:
            self.player_list.clear()
            if self.settings.tracked_teams:
                self.banner.show_info(
                    tr(
                        "No players to display. Check that initial stats (stats file) are imported "
                        "and that custom teams have their abbreviation and name registered in Settings."
                    )
                )
            else:
                self.banner.show_info(
                    tr(
                        "No players to display. Run initial setup or import boxscores, "
                        "then check again."
                    )
                )
            return
        self.banner.hide()
        self._apply_player_filter()

    def refresh_players(self) -> None:
        """Backward-compatible alias."""
        self.reload_players()

    def _apply_player_filter(self) -> None:
        needle = self.player_search.text().strip().lower()
        position_group = str(self.position_combo.currentData() or "")
        previous_id = self._selected_player_id()
        self.player_list.blockSignals(True)
        self.player_list.clear()
        for player in self._players:
            if not player_matches_position_group(player, position_group):
                continue
            full = str(player.get("full_name") or "")
            short = str(player.get("short_name") or "")
            display = best_display_name(full, short)
            player_id = str(player["player_id"])
            haystack = " ".join((display, full, short, player_id)).lower()
            if needle and needle not in haystack:
                continue
            item = QListWidgetItem(format_player_list_label(player))
            item.setData(Qt.ItemDataRole.UserRole, int(player["player_id"]))
            self.player_list.addItem(item)
        if previous_id is not None:
            for row in range(self.player_list.count()):
                item = self.player_list.item(row)
                if item and int(item.data(Qt.ItemDataRole.UserRole)) == previous_id:
                    self.player_list.setCurrentRow(row)
                    break
        elif self.player_list.count():
            self.player_list.setCurrentRow(0)
        self.player_list.blockSignals(False)
        if self.player_list.currentRow() >= 0:
            self._refresh_player_stats()
        else:
            self.player_header.setText(tr("Please select a player."))
            self.info_label.setText("")
            self.batting_table.setRowCount(0)
            self.pitching_table.setRowCount(0)
            self.milestone_timeline.load_player(None)

    def _on_list_selection(self, row: int) -> None:
        if row >= 0:
            self._refresh_player_stats()

    def _selected_player_id(self) -> int | None:
        item = self.player_list.currentItem()
        if not item:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _selected_player(self) -> dict | None:
        player_id = self._selected_player_id()
        if player_id is None:
            return None
        return self._players_by_id.get(player_id)

    def _refresh_player_stats(self) -> None:
        player = self._selected_player()
        player_id = self._selected_player_id()
        if player_id is None or player is None:
            self.player_header.setText(tr("Please select a player."))
            self.info_label.setText("")
            self.batting_table.setRowCount(0)
            self.pitching_table.setRowCount(0)
            self.milestone_timeline.load_player(None)
            return

        mapper = load_korean_name_mapper()
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir
        )
        korean_name = korean_display_for_player(
            mapper,
            full_name=str(player.get("full_name") or ""),
            player_id=player_id,
            roster_names=roster_names,
        )
        self.player_header.setText(format_player_header(player, korean_name=korean_name))
        self.milestone_timeline.load_player(player_id)

        career_mode = self._career_mode or self.season_combo.currentData() == "career"
        if career_mode:
            coverage = get_init_season_coverage(self.aggregator.conn)
            has_init = self.aggregator.player_has_init_stats(player_id)
            if has_init:
                self.info_label.setText(
                    tr("Career stats (init through {coverage} season + boxscores)").format(
                        coverage=coverage
                    )
                )
            else:
                self.info_label.setText(tr("No initial stats — boxscore records only"))
            self._fill_career_tables(player_id)
        else:
            season = int(self.season_combo.currentData())
            batting = self.aggregator.get_batting_season(player_id, season)
            pitching = self.aggregator.get_pitching_season(player_id, season)
            from_init = (
                (batting or {}).get("_source") == "init"
                or (pitching or {}).get("_source") == "init"
            )
            if from_init:
                self.info_label.setText(
                    tr("{season} season stats (initial value — stats file, no boxscores)").format(
                        season=season
                    )
                )
            else:
                self.info_label.setText(
                    tr("{season} season stats (double-click: game-by-game log)").format(
                        season=season
                    )
                )
            self._fill_season_tables(player_id, season)

    def _fill_season_tables(self, player_id: int, season: int) -> None:
        batting = self.aggregator.get_batting_season(player_id, season)
        pitching = self.aggregator.get_pitching_season(player_id, season)
        self._set_stat_row(
            self.batting_table,
            batting,
            {
                "G": "games_played",
                "AB": "ab",
                "H": "h",
                "2B": "doubles",
                "3B": "triples",
                "HR": "hr",
                "RBI": "rbi",
                "R": "r",
                "BB": "bb",
                "K": "k",
                "SB": "sb",
                "AVG": "avg",
                "OBP": "obp",
                "SLG": "slg",
                "OPS": "ops",
            },
        )
        self._set_stat_row(
            self.pitching_table,
            pitching,
            {
                "G": "games",
                "GS": "games",
                "W": "wins",
                "L": "losses",
                "SV": "saves",
                "IP": "ip_display",
                "K": "k",
                "BB": "bb",
                "HR": "hr",
                "ERA": "era",
                "WHIP": "whip",
                "CG": "cg",
                "SHO": "sho",
            },
        )

    def _fill_career_tables(self, player_id: int) -> None:
        batting = self.aggregator.get_player_career_batting_row(player_id)
        pitching = self.aggregator.get_player_career_pitching_row(player_id)
        self._set_stat_row(
            self.batting_table,
            batting,
            {
                "G": "g",
                "AB": "ab",
                "H": "h",
                "2B": "doubles",
                "3B": "triples",
                "HR": "hr",
                "RBI": "rbi",
                "R": "r",
                "BB": "bb",
                "K": "k",
                "SB": "sb",
                "AVG": "avg",
            },
        )
        self._set_stat_row(
            self.pitching_table,
            pitching,
            {
                "G": "g",
                "GS": "gs",
                "W": "w",
                "L": "l",
                "SV": "s",
                "IP": "ip",
                "K": "k",
                "BB": "bb",
                "HR": "hr",
                "ERA": "era",
                "WHIP": "whip",
                "CG": "cg",
                "SHO": "sho",
            },
        )

    @staticmethod
    def _set_stat_row(table: SortableTable, data: dict | None, mapping: dict[str, str]) -> None:
        if not data:
            table.setRowCount(0)
            return
        row = [tr("Stats")] + [data.get(mapping[col], "") for col in mapping]
        table.populate([row])

    def _open_game_logs(self, _row: int, _col: int) -> None:
        if self._career_mode:
            return
        player_id = self._selected_player_id()
        player = self._selected_player()
        if player_id is None or player is None:
            return
        season_data = self.season_combo.currentData()
        if season_data == "career":
            return
        name = best_display_name(player.get("full_name"), player.get("short_name"))
        PlayerGameLogDialog(
            self.aggregator,
            self.settings,
            player_id,
            name,
            int(season_data),
            self,
        ).exec()

    def _on_mlb_only_toggled(self, checked: bool) -> None:
        self.settings.import_mlb_only = checked
        self.settings_manager.save(self.settings)

    def start_import(self) -> None:
        self.settings.import_mlb_only = self.mlb_only_checkbox.isChecked()
        boxscore_dir = self.settings.boxscore_dir
        if not boxscore_dir:
            self.banner.show_warning(
                tr("Boxscore folder not configured. Click the status bar at the bottom to select a league.")
            )
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
        self._reload_seasons()
        self.reload_players()

        result = payload.batch
        parts = [tr("{count} games added").format(count=result.imported)]
        if result.skipped_non_mlb:
            parts.append(tr("{count} non-MLB skipped").format(count=result.skipped_non_mlb))
        if payload.milestones_recorded:
            team_count = sum(
                1
                for item in payload.milestones
                if item.milestone.scope.startswith("team_")
            )
            personal_count = payload.milestones_recorded - team_count
            milestone_parts = []
            if personal_count:
                milestone_parts.append(tr("Personal: {count}").format(count=personal_count))
            if team_count:
                milestone_parts.append(tr("Team: {count}").format(count=team_count))
            label = " · ".join(milestone_parts) if milestone_parts else str(
                payload.milestones_recorded
            )
            parts.append(tr("{count} milestones achieved").format(count=label))
        message = " · ".join(parts)
        self.import_finished.emit(message)

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
