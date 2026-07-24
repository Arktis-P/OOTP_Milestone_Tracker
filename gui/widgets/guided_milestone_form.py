"""Guided form helpers shared by manual and message-review milestone flows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import date
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


CATEGORY_DISPLAY_KEYS: dict[str, str] = {
    "trade": "Trade",
    "fa_contract": "FA contract",
    "extension_contract": "Extension contract",
    "injury": "Injury",
    "award_mvp": "Most Valuable Player award",
    "award_cy_young": "Cy Young award",
    "award_great_glove": "Great Glove award",
    "award_platinum_stick": "Platinum Stick award",
    "award_rookie_of_year": "Rookie of the Year award",
    "award_player_of_month": "Player of the Month award",
    "award_all_star": "All-Star selection",
    "postseason_division": "Division title",
    "postseason_world_series": "World Series title",
    "hall_of_fame": "Hall of Fame induction",
    "trade_deadline_news": "Trade deadline news",
    "retirement": "Retirement news",
    "postseason_wildcard": "Wild card news",
    "postseason_playoff_clinch": "Playoff clinch news",
    "award_all_star_voting": "All-Star voting news",
    "hall_of_fame_voting": "Hall of Fame voting news",
    "award_player_of_week": "Player of the Week news",
    "unknown": "Unrecognized message",
}

REASON_DISPLAY_KEYS: dict[str, str] = {
    "trade_deadline_not_a_transaction": "Trade deadline article; no transaction record.",
    "retirement_milestone_undefined": "Retirement article; no configured milestone record.",
    "postseason_wildcard_key_mismatch": "Wild card article; no matching milestone key.",
    "postseason_playoff_clinch_no_key": "Playoff clinch article; no configured milestone key.",
    "all_star_voting_not_final": "All-Star voting article; wait for final roster.",
    "hall_of_fame_voting_not_final": "Hall of Fame voting article; wait for final result.",
    "player_of_week_not_recorded": "Player of the Week is intentionally not recorded.",
    "unrecognized_message_type": "Message type is not recognized.",
    "message_date_required": "Message date is required before saving.",
    "tracked team not involved": "Tracked team is not involved.",
    "duplicate": "Already reflected in records.",
    "changed_source": "Source text changed; review again before saving.",
    "file_read_failed": "Source file could not be read.",
    "Excluded by reviewer.": "Excluded by reviewer.",
    "Date confirmation required before saving.": "Date confirmation required before saving.",
}

STATUS_DISPLAY_KEYS: dict[str, str] = {
    "candidate": "Candidate",
    "approved": "Approved",
    "applied": "Already applied",
    "excluded": "Excluded",
    "date_needed": "Date needed",
    "error": "Error",
}

SOURCE_DISPLAY_KEYS: dict[str, str] = {
    "boxscore_auto": "Boxscore automatic",
    "message_auto": "Message automatic",
    "manual": "Manual entry",
    "season_final": "Season finalization",
    "migration": "Legacy migrated record",
    "validation": "Validation",
}

FIELD_DISPLAY_KEYS: dict[str, str] = {
    "target": "Record target",
    "achieved_date": "Date",
    "player_id": "Player",
    "player_name": "Player",
    "team": "Team",
    "milestone_key": "Record type",
    "season": "Season",
    "achieved_value": "Value",
    "games_at_achievement": "Games at achievement",
    "opponent_team": "Opponent team",
    "opponent_player": "Opponent player",
    "description": "Description",
    "notes": "Original message ID",
    "joining_players": "Joining players",
    "leaving_players": "Leaving players",
    "event_type": "Move type",
    "join_team": "Joining team",
    "counterpart_team": "Counterpart team",
    "fa_is_retention": "Retained by same team",
    "injury_label": "Injury",
    "duration": "Duration",
}


def display_category(category: str) -> str:
    return tr(CATEGORY_DISPLAY_KEYS.get(category, category.replace("_", " ").title()))


def display_reason(reason: str | None) -> str:
    if not reason:
        return ""
    return tr(REASON_DISPLAY_KEYS.get(reason, reason.replace("_", " ").capitalize()))


def display_status(status: str | None) -> str:
    if not status:
        return ""
    return tr(STATUS_DISPLAY_KEYS.get(status, status.replace("_", " ").title()))


def display_source(source: str | None) -> str:
    if not source:
        return ""
    return tr(SOURCE_DISPLAY_KEYS.get(source, source.replace("_", " ").title()))


def display_field(field_name: str) -> str:
    return tr(FIELD_DISPLAY_KEYS.get(field_name, field_name.replace("_", " ").title()))


def display_field_value(field_name: str, value: Any) -> str:
    text = _value_to_text(value)
    if field_name in {"milestone_key", "category", "event_type"}:
        return display_category(text)
    if field_name == "target":
        return tr("Player") if text == "player" else tr("Team") if text == "team" else text
    if field_name == "fa_is_retention":
        if value is None:
            return ""
        return tr("Yes") if bool(value) else tr("No")
    return text


def form_type_label(form: Any) -> str:
    name = type(form).__name__
    if name == "ManualMilestoneFormData":
        return tr("Milestone or award record")
    if name == "ManualTransferFormData":
        return tr("Team move record")
    if name == "ManualInjuryFormData":
        return tr("Injury record")
    return tr("Extracted record")


def editable_field_values(form: Any) -> dict[str, str]:
    if is_dataclass(form):
        return {
            field.name: _value_to_text(getattr(form, field.name))
            for field in fields(form)
        }
    return {
        key: _value_to_text(value)
        for key, value in vars(form).items()
        if not key.startswith("_")
    }


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class GuidedMilestoneForm(QWidget):
    """Simple label/value editor that hides technical dataclass field names."""

    def __init__(
        self,
        forms: Iterable[Any] = (),
        *,
        intro: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._forms = list(forms)

        layout = QVBoxLayout(self)
        self.hint_label = QLabel(intro or tr("Review and correct only the fields needed for this record."))
        self.hint_label.setObjectName("mutedLabel")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.form_combo = QComboBox()
        self.form_combo.currentIndexChanged.connect(self._load_selected_form)
        layout.addWidget(self.form_combo)

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("guidedMilestoneFormTable")
        self.table.setHorizontalHeaderLabels([tr("Field"), tr("Value")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.set_forms(self._forms)

    def set_forms(self, forms: Iterable[Any]) -> None:
        self._forms = list(forms)
        self.form_combo.blockSignals(True)
        self.form_combo.clear()
        for index, form in enumerate(self._forms):
            self.form_combo.addItem(f"{index + 1}. {form_type_label(form)}", index)
        self.form_combo.blockSignals(False)
        self._load_selected_form()

    def selected_form_index(self) -> int:
        data = self.form_combo.currentData()
        return int(data) if data is not None else 0

    def edited_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            label_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if label_item is None:
                continue
            key = label_item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(key, str):
                continue
            values[key] = value_item.text() if value_item is not None else ""
        return values

    def _load_selected_form(self) -> None:
        index = self.selected_form_index()
        if not (0 <= index < len(self._forms)):
            self.table.setRowCount(0)
            return
        values = editable_field_values(self._forms[index])
        self.table.setRowCount(len(values))
        for row, (key, value) in enumerate(values.items()):
            label_item = QTableWidgetItem(display_field(key))
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, label_item)
            self.table.setItem(row, 1, QTableWidgetItem(value))
