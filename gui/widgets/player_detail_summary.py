"""Compact read-only player detail summary for the Stats screen."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.milestone.prediction_store import render_season_note
from core.stats.player_detail import PlayerDetail, PlayerEvent


class PlayerDetailSummary(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._events: list[PlayerEvent] = []

        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setObjectName("mutedLabel")

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setVisible(False)

        self.events_list = QListWidget()
        self.events_list.setMaximumHeight(118)
        self.events_list.itemClicked.connect(self._on_event_clicked)

        self.streaks_label = QLabel()
        self.streaks_label.setWordWrap(True)
        self.streaks_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.next_label = QLabel()
        self.next_label.setWordWrap(True)
        self.next_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(_section(tr("Recent Events")), 0, 0)
        grid.addWidget(_section(tr("Active Streaks")), 0, 1)
        grid.addWidget(_section(tr("Next Milestones")), 0, 2)
        grid.addWidget(self.events_list, 1, 0)
        grid.addWidget(_summary_box(self.streaks_label), 1, 1)
        grid.addWidget(_summary_box(self.next_label), 1, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.status_label)
        layout.addLayout(grid)

    def load_detail(self, detail: PlayerDetail) -> None:
        self._events = list(detail.events)
        self.meta_label.setText(self._meta_text(detail))
        self.status_label.setText(self._status_text(detail.status))
        self.status_label.setVisible(bool(detail.status))

        self.events_list.clear()
        if detail.events:
            self.events_list.setEnabled(True)
            for event in detail.events:
                item = QListWidgetItem(_event_text(event))
                item.setData(Qt.ItemDataRole.UserRole, event)
                if event.game_id:
                    item.setToolTip(tr("Click to open the game log."))
                self.events_list.addItem(item)
        else:
            self.events_list.setEnabled(False)
            self.events_list.addItem(tr("No recent player events."))

        if detail.active_streaks:
            self.streaks_label.setText(
                "\n".join(
                    f"{item.label}: {item.display_value} {item.unit}"
                    + (f" ({item.last_date})" if item.last_date else "")
                    for item in detail.active_streaks
                )
            )
        else:
            self.streaks_label.setText(tr("No active streaks for this season."))

        if detail.next_milestones:
            lines = []
            for item in detail.next_milestones:
                remaining = _format_number(item.remaining)
                current = _format_number(item.current_value)
                threshold = _format_number(item.threshold)
                lines.append(
                    f"{item.milestone_label}: {current}/{threshold}, "
                    f"{remaining} {tr('remaining')} - {render_season_note(item.season_note)}"
                )
            self.next_label.setText("\n".join(lines))
        else:
            self.next_label.setText(tr("No cached tracked milestones for this player."))

    def clear(self, message: str | None = None) -> None:
        self._events.clear()
        self.meta_label.setText("")
        self.status_label.setText(message or tr("Please select a player."))
        self.status_label.setVisible(True)
        self.events_list.clear()
        self.events_list.setEnabled(False)
        self.events_list.addItem(tr("No recent player events."))
        self.streaks_label.setText(tr("No active streaks for this season."))
        self.next_label.setText(tr("No cached tracked milestones for this player."))

    def _meta_text(self, detail: PlayerDetail) -> str:
        team = detail.current_team or tr("Unknown team")
        position = detail.position or tr("Unknown position")
        return tr("Team: {team} | Position: {position} | Season: {season}").format(
            team=team,
            position=position,
            season=detail.season,
        )

    def _status_text(self, status: str) -> str:
        if status == "missing_player":
            return tr("Player details are unavailable. The player may have been deleted.")
        if status == "select_player":
            return tr("Please select a player.")
        if status == "empty_detail":
            return tr(
                "No recent events, active streaks, or cached milestone targets for this player."
            )
        return ""

    def _on_event_clicked(self, item: QListWidgetItem) -> None:
        event = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(event, PlayerEvent) or not event.game_id:
            return
        logs_dir = self.settings.game_logs_dir
        if not logs_dir:
            QMessageBox.information(self, tr("Game Log"), tr("Game log directory is not configured."))
            return
        log_path = Path(logs_dir) / f"log_{event.game_id}.html"
        if not log_path.is_file():
            QMessageBox.information(
                self,
                tr("Game Log"),
                tr("File not found:\n{path}").format(path=log_path),
            )
            return
        webbrowser.open(log_path.resolve().as_uri())


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionLabel")
    return label


def _summary_box(child: QLabel) -> QFrame:
    frame = QFrame()
    frame.setObjectName("toolRow")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.addWidget(child)
    return frame


def _event_text(event: PlayerEvent) -> str:
    prefix = {
        "milestone": tr("Milestone"),
        "award": tr("Award"),
        "transfer": tr("Transfer"),
        "injury": tr("Injury"),
        "streak": tr("Streak"),
        "other": tr("Event"),
    }.get(event.kind, tr("Event"))
    bits = [event.date, prefix, event.label]
    text = " | ".join(bit for bit in bits if bit)
    if event.description:
        text = f"{text} - {event.description}"
    return text


def _format_number(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.3f}".rstrip("0").rstrip(".")
