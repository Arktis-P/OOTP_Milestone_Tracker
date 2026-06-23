"""Per-game batting/pitching log drilldown."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.config import AppSettings
from core.i18n import tr
from core.stats.aggregator import Aggregator
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box, muted_label
from gui.widgets.card_panel import CardPanel
from gui.widgets.table_widgets import SortableTable


class PlayerGameLogDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        player_id: int,
        player_name: str,
        season: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.player_id = player_id
        self.season = season

        self.setWindowTitle(
            tr("{player_name} — Season {season} Game Log").format(
                player_name=player_name, season=season
            )
        )
        self.resize(*scale_size(900, 520))

        tabs = QTabWidget()
        self._batting_table = SortableTable(
            [tr("Date"), tr("Opponent"), "AB", "H", "HR", "RBI", "BB", "K", "AVG"]
        )
        self._pitching_table = SortableTable(
            [tr("Date"), tr("Opponent"), "IP", "H", "ER", "BB", "K", "HR", tr("Result")]
        )
        tabs.addTab(self._batting_table, tr("Batting"))
        tabs.addTab(self._pitching_table, tr("Pitching"))

        self._batting_rows: list[dict] = []
        self._pitching_rows: list[dict] = []

        self._populate_batting()
        self._populate_pitching()

        self._batting_table.cellDoubleClicked.connect(self._open_log)
        self._pitching_table.cellDoubleClicked.connect(self._open_log)

        log_card = CardPanel(tr("Game-by-Game Log"))
        log_card.add_widget(tabs)

        buttons = make_button_box(close=True, cancel=False)
        buttons.rejected.connect(self.accept)

        layout = init_dialog_layout(self)
        layout.addWidget(muted_label(tr("Double-click date: open game log HTML"), wrap=False))
        layout.addWidget(log_card, stretch=1)
        add_dialog_footer(layout, buttons)

    def _populate_batting(self) -> None:
        self._batting_rows = self.aggregator.get_player_batting_game_logs(
            self.player_id, self.season
        )
        rows = []
        for row in self._batting_rows:
            avg = row.get("season_avg")
            if avg is None and row.get("ab"):
                avg = round(row["h"] / row["ab"], 3)
            rows.append(
                [
                    row["date"],
                    row.get("opponent", ""),
                    row.get("ab", 0),
                    row.get("h", 0),
                    row.get("hr", 0),
                    row.get("rbi", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    avg if avg is not None else "",
                ]
            )
        self._batting_table.populate(rows)

    def _populate_pitching(self) -> None:
        self._pitching_rows = self.aggregator.get_player_pitching_game_logs(
            self.player_id, self.season
        )
        rows = []
        for row in self._pitching_rows:
            decision = row.get("decision") or ""
            if row.get("save"):
                decision = "SV"
            rows.append(
                [
                    row["date"],
                    row.get("opponent", ""),
                    row.get("ip", ""),
                    row.get("h", 0),
                    row.get("er", 0),
                    row.get("bb", 0),
                    row.get("k", 0),
                    row.get("hr", 0),
                    decision,
                ]
            )
        self._pitching_table.populate(rows)

    def _open_log(self, row: int, _column: int) -> None:
        table = self.sender()
        if table is self._batting_table:
            logs = self._batting_rows
        else:
            logs = self._pitching_rows
        if row < 0 or row >= len(logs):
            return
        game_id = logs[row].get("game_id")
        logs_dir = self.settings.game_logs_dir
        if not game_id or not logs_dir:
            return
        log_path = Path(logs_dir) / f"log_{game_id}.html"
        if log_path.is_file():
            webbrowser.open(log_path.resolve().as_uri())
