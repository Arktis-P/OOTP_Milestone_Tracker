"""Milestone prediction tab."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.milestone.predictor import MilestonePredictor
from core.stats.aggregator import Aggregator
from gui.widgets.table_widgets import TablePanel


class PredictView(QWidget):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings

        self.refresh_button = QPushButton("예측 갱신")
        self.refresh_button.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(self.refresh_button)
        controls.addStretch()
        controls.addWidget(QLabel("현재 페이스 기준 시즌 말 예상치"))

        self.table_panel = TablePanel(
            ["선수", "마일스톤", "현재", "예상", "잔여", "경기", "페이스"],
            placeholder="선수 검색...",
        )

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.table_panel)

        self.refresh()

    def refresh(self) -> None:
        checker = MilestoneChecker(self.aggregator, self.milestones)
        predictor = MilestonePredictor(checker, self.settings.current_season)
        predictions = predictor.predict_all()

        rows = []
        for item in predictions:
            rows.append(
                [
                    item.player_name,
                    item.milestone.label,
                    f"{item.current_value:.1f}",
                    f"{item.projected_value:.1f}" if item.projected_value is not None else "-",
                    f"{item.remaining:.1f}",
                    item.games_played,
                    "달성 가능" if item.on_pace else "미달",
                ]
            )
        self.table_panel.table.populate(rows)
