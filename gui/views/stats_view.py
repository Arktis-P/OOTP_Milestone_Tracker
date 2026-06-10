"""Player and team statistics tab."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.config import AppSettings
from core.stats.aggregator import Aggregator
from gui.widgets.table_widgets import TablePanel


class StatsView(QWidget):
    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["시즌 타격", "통산 타격", "시즌 투구", "통산 투구"])
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("기록 유형:"))
        controls.addWidget(self.scope_combo)
        controls.addStretch()

        self.table_panel = TablePanel(
            ["선수", "팀", "기록"],
            placeholder="선수 검색...",
        )

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.table_panel)

        self.refresh()

    def refresh(self) -> None:
        scope = self.scope_combo.currentText()
        season = self.settings.current_season

        if scope == "시즌 타격":
            data = self.aggregator.get_season_batting_totals(season)
            columns = ["선수", "팀", "AB", "H", "HR", "RBI", "BB", "SO", "SB"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ab", 0),
                    row.get("h", 0),
                    row.get("hr", 0),
                    row.get("rbi", 0),
                    row.get("bb", 0),
                    row.get("so", 0),
                    row.get("sb", 0),
                ]
                for row in data
            ]
        elif scope == "통산 타격":
            data = self.aggregator.get_career_batting_totals()
            columns = ["선수", "팀", "AB", "H", "HR", "RBI", "BB", "SO", "SB"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ab", 0),
                    row.get("h", 0),
                    row.get("hr", 0),
                    row.get("rbi", 0),
                    row.get("bb", 0),
                    row.get("so", 0),
                    row.get("sb", 0),
                ]
                for row in data
            ]
        elif scope == "시즌 투구":
            data = self.aggregator.get_season_pitching_totals(season)
            columns = ["선수", "팀", "IP", "H", "ER", "BB", "SO", "W", "L", "SV"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ip", 0),
                    row.get("h", 0),
                    row.get("er", 0),
                    row.get("bb", 0),
                    row.get("so", 0),
                    row.get("w", 0),
                    row.get("l", 0),
                    row.get("sv", 0),
                ]
                for row in data
            ]
        else:
            data = self.aggregator.get_career_pitching_totals()
            columns = ["선수", "팀", "IP", "H", "ER", "BB", "SO", "W", "L", "SV"]
            rows = [
                [
                    row["name"],
                    row.get("team") or "",
                    row.get("ip", 0),
                    row.get("h", 0),
                    row.get("er", 0),
                    row.get("bb", 0),
                    row.get("so", 0),
                    row.get("w", 0),
                    row.get("l", 0),
                    row.get("sv", 0),
                ]
                for row in data
            ]

        self.table_panel.table.setColumnCount(len(columns))
        self.table_panel.table.setHorizontalHeaderLabels(columns)
        self.table_panel.table.populate(rows)
