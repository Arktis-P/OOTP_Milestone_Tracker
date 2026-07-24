"""Guided form widgets shared by manual and message-review milestone flows.

``GuidedRecordEditor`` is the real, typed editor (QDateEdit with a calendar
popup, player/team autocomplete, milestone/transfer/injury pages) used by the
"enter one at a time" dialogs in ``single_record_dialogs.py``.

``GuidedMilestoneForm`` is the widget message-review edits go through. Its
constructor signature is unchanged for backward compatibility (it is
constructed today as ``GuidedMilestoneForm(item.parsed.forms, parent=self)``
by ``gui/views/message_review_view.py``, which this package does not own).
The visible, interactive widget is always the real typed
``GuidedRecordEditor``. When a caller also supplies ``aggregator``/
``settings`` (optionally ``milestones``) the editor's player/team fields get
full autocomplete, matching manual single-record entry; without them the
same typed fields still work as plain editable combo/date widgets. A hidden
``QTableWidget`` mirror is kept in sync only so older callers/tests that
inspect translated field labels via ``.table`` keep working unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import date
from typing import Any, Literal

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.implementation import is_award_milestone, manual_entry_hint, requires_external_data
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    TRANSFER_EVENT_LABELS,
    build_injury_description,
    build_trade_description,
    get_achieved_value_candidates,
    milestones_for_manual_entry,
    parse_player_name_list,
    scope_needs_games_at_achievement,
    scope_needs_season,
    season_if_in_season,
    validate_manual_entry,
    validate_manual_injury,
    validate_manual_transfer,
)
from core.roster.player_registry import PlayerRegistry
from gui.ui_compact import hint_style
from gui.widgets.manual_entry_fields import (
    apply_completer,
    canonical_player_text,
    configure_mlb_team_combo,
    configure_player_combo,
    configure_player_multipick_combo,
    configure_tracked_team_combo,
    ensure_player_id_from_combo,
    fill_tracked_team_combo,
    first_tracked_team_name,
    tracked_team_names,
)


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
    "excluded_by_reviewer": "Excluded by reviewer.",
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
    hidden = {"source_id", "source", "category", "status", "dataclass_type", "class_name"}
    if is_dataclass(form):
        return {
            field.name: _value_to_text(getattr(form, field.name))
            for field in fields(form)
            if field.name not in hidden
        }
    return {
        key: _value_to_text(value)
        for key, value in vars(form).items()
        if not key.startswith("_") and key not in hidden
    }


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _required_label(text: str) -> str:
    """Form label with a red asterisk marking a required field."""
    return f'{text} <span style="color:#d32f2f; font-weight:bold">*</span>'


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            unique.append(error)
    return unique


_NO_DATE = QDate(1900, 1, 1)


def _qdate_to_date(qdate: QDate) -> date | None:
    if qdate == _NO_DATE:
        return None
    return date(qdate.year(), qdate.month(), qdate.day())


def _date_to_qdate(value: date | None) -> QDate:
    if value is None:
        return _NO_DATE
    return QDate(value.year, value.month, value.day)


def _configure_date_edit(date_edit: QDateEdit) -> None:
    date_edit.setCalendarPopup(True)
    date_edit.setDisplayFormat("yyyy-MM-dd")
    date_edit.setMinimumDate(_NO_DATE)
    date_edit.setSpecialValueText("")
    date_edit.setDate(QDate.currentDate())


def _qdate_value(date_edit: QDateEdit) -> str:
    parsed = _qdate_to_date(date_edit.date())
    return parsed.isoformat() if parsed is not None else ""


def _format_achieved_value(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _optional_int(text: str) -> int | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class _MilestoneAwardPage(QWidget):
    """Typed milestone/award editor page: target, date, player/team, value."""

    def __init__(
        self,
        aggregator: Any,
        settings: Any,
        milestones: MilestoneDefinitions | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.milestones = milestones
        self._category: Literal["milestone", "award"] = "milestone"

        layout = QVBoxLayout(self)

        self.player_radio = QRadioButton(tr("Personal"))
        self.team_radio = QRadioButton(tr("Team"))
        self.player_radio.setChecked(True)
        self.player_radio.toggled.connect(self._on_target_changed)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel(tr("Target:")))
        target_row.addWidget(self.player_radio)
        target_row.addWidget(self.team_radio)
        target_row.addStretch()

        self.date_edit = QDateEdit()
        _configure_date_edit(self.date_edit)

        self.player_combo = QComboBox()
        if aggregator is not None and settings is not None:
            configure_player_combo(self.player_combo, aggregator, settings)
        else:
            self.player_combo.setEditable(True)
        line = self.player_combo.lineEdit()
        if line is not None:
            line.setPlaceholderText(tr("Enter full name or select from list (e.g., Dong-ju Moon)"))
        self.add_player_button = QPushButton(tr("+ Add Player"))
        self.add_player_button.setEnabled(aggregator is not None)
        self.add_player_button.clicked.connect(self._on_add_player)

        player_row = QHBoxLayout()
        player_row.addWidget(self.player_combo, stretch=1)
        player_row.addWidget(self.add_player_button)
        self.player_row_widget = QWidget()
        self.player_row_widget.setLayout(player_row)

        self.team_combo = QComboBox()
        if settings is not None:
            fill_tracked_team_combo(self.team_combo, settings)
        else:
            self.team_combo.setEditable(True)
        self.team_row_widget = QWidget()
        team_layout = QHBoxLayout(self.team_row_widget)
        team_layout.setContentsMargins(0, 0, 0, 0)
        team_layout.addWidget(self.team_combo)

        self.milestone_combo = QComboBox()
        self.milestone_combo.setEditable(True)
        self.milestone_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.milestone_combo.currentIndexChanged.connect(self._on_milestone_changed)
        apply_completer(self.milestone_combo)

        self.manual_hint = QLabel("")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setStyleSheet(hint_style())

        self.season_edit = QLineEdit()
        self.season_edit.setPlaceholderText(tr("Auto (date year)"))
        self.season_label = QLabel(tr("Season:"))
        self.season_row_widget = QWidget()
        season_layout = QHBoxLayout(self.season_row_widget)
        season_layout.setContentsMargins(0, 0, 0, 0)
        season_layout.addWidget(self.season_edit)

        self.games_edit = QLineEdit()
        self.games_edit.setPlaceholderText(tr("Games played up to this point"))
        self.games_label = QLabel(tr("Games in:"))
        self.games_row_widget = QWidget()
        games_layout = QHBoxLayout(self.games_row_widget)
        games_layout.setContentsMargins(0, 0, 0, 0)
        games_layout.addWidget(self.games_edit)

        self.value_combo = QComboBox()
        self.value_combo.setEditable(True)
        self.value_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self.opponent_team_edit = QComboBox()
        if settings is not None:
            configure_mlb_team_combo(self.opponent_team_edit, settings)
        else:
            self.opponent_team_edit.setEditable(True)

        self.opponent_player_edit = QComboBox()
        if aggregator is not None and settings is not None:
            configure_player_combo(self.opponent_player_edit, aggregator, settings)
        else:
            self.opponent_player_edit.setEditable(True)

        self.description_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        self.form_layout = QFormLayout()
        self.form_layout.addRow(_required_label(tr("Date:")), self.date_edit)
        self.form_layout.addRow(_required_label(tr("Player:")), self.player_row_widget)
        self.form_layout.addRow(_required_label(tr("Team:")), self.team_row_widget)
        self.form_layout.addRow(_required_label(tr("Milestone:")), self.milestone_combo)
        self.form_layout.addRow(self.season_label, self.season_row_widget)
        self.form_layout.addRow(self.games_label, self.games_row_widget)
        self.form_layout.addRow(_required_label(tr("Achieved Value:")), self.value_combo)
        self.form_layout.addRow(tr("Opponent:"), self.opponent_team_edit)
        self.form_layout.addRow(tr("Opp. Player:"), self.opponent_player_edit)
        self.form_layout.addRow(tr("Description:"), self.description_edit)
        self.form_layout.addRow(tr("Notes:"), self.notes_edit)

        layout.addLayout(target_row)
        layout.addWidget(self.manual_hint)
        layout.addLayout(self.form_layout)
        layout.addStretch()

        self._reload_milestones()
        self._on_target_changed()

    def set_category(self, category: Literal["milestone", "award"]) -> None:
        self._category = category
        self.games_label.setText(
            _required_label(tr("Games in:")) if category != "award" else tr("Games in:")
        )
        self.form_layout.setRowVisible(self.opponent_player_edit, category != "award")
        self._reload_milestones()

    def _reload_milestones(self) -> None:
        pool = self._milestone_pool()
        current_key = self.milestone_combo.currentData()
        self.milestone_combo.blockSignals(True)
        self.milestone_combo.clear()
        for milestone in pool:
            self.milestone_combo.addItem(milestone.label, milestone.key)
        if current_key:
            index = self.milestone_combo.findData(current_key)
            if index >= 0:
                self.milestone_combo.setCurrentIndex(index)
        self.milestone_combo.blockSignals(False)
        self._on_milestone_changed()

    def _milestone_pool(self) -> list[MilestoneDefinition]:
        if self.milestones is None:
            return []
        target: Literal["player", "team"] = "player" if self.player_radio.isChecked() else "team"
        return milestones_for_manual_entry(
            self.milestones.all_milestones, target, category=self._category
        )

    def _on_target_changed(self) -> None:
        is_player = self.player_radio.isChecked()
        self.player_row_widget.setVisible(is_player)
        self.team_row_widget.setVisible(not is_player)
        self._reload_milestones()

    def _selected_milestone(self) -> MilestoneDefinition | None:
        if self.milestones is None:
            return None
        key = self.milestone_combo.currentData()
        if not key:
            return None
        return self.milestones.get_by_key(str(key))

    def selected_milestone(self) -> MilestoneDefinition | None:
        return self._selected_milestone()

    def _update_milestone_hint(self) -> None:
        milestone = self._selected_milestone()
        if self._category == "award":
            self.manual_hint.setText(
                manual_entry_hint(milestone)
                if milestone is not None
                else tr("Awards, league leaders, and other items not auto-detected from boxscores.")
            )
            return
        if milestone is not None and requires_external_data(milestone):
            self.manual_hint.setText(manual_entry_hint(milestone))
        else:
            self.manual_hint.setText(
                tr("Can be auto-detected from boxscores, but use this to supplement or correct.")
            )

    def _on_milestone_changed(self) -> None:
        milestone = self._selected_milestone()
        self._update_milestone_hint()
        scope = milestone.scope if milestone is not None else None
        self.season_row_widget.setVisible(scope is None or scope_needs_season(scope))
        self.season_label.setVisible(scope is None or scope_needs_season(scope))
        self.games_row_widget.setVisible(scope is None or scope_needs_games_at_achievement(scope))
        self.games_label.setVisible(scope is None or scope_needs_games_at_achievement(scope))

        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        if milestone is not None:
            for candidate in get_achieved_value_candidates(milestone):
                self.value_combo.addItem(candidate)
            if self.value_combo.count():
                self.value_combo.setCurrentIndex(0)
        self.value_combo.blockSignals(False)

    def _on_add_player(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("Add Player"), tr("Enter full name (e.g., Dong-ju Moon):")
        )
        if not ok:
            return
        try:
            if self.aggregator is None:
                return
            player_id = PlayerRegistry(self.aggregator).add_manual_player(name)
        except ValueError as exc:
            QMessageBox.warning(self, tr("Input Error"), str(exc))
            return
        for combo in (self.player_combo, self.opponent_player_edit):
            configure_player_combo(combo, self.aggregator, self.settings)
        index = self.player_combo.findData(player_id)
        if index >= 0:
            self.player_combo.setCurrentIndex(index)

    def set_form(self, form: ManualMilestoneFormData) -> None:
        milestone = self.milestones.get_by_key(form.milestone_key) if self.milestones else None
        if milestone is not None:
            self.set_category("award" if is_award_milestone(milestone) else "milestone")

        self.date_edit.setDate(_date_to_qdate(form.achieved_date))

        if form.target == "team":
            self.team_radio.setChecked(True)
        else:
            self.player_radio.setChecked(True)
        if form.target == "player" and form.player_id is not None:
            index = self.player_combo.findData(form.player_id)
            if index >= 0:
                self.player_combo.setCurrentIndex(index)
            else:
                self.player_combo.setCurrentText(self._player_display_name(form.player_id))
        elif form.target == "team" and form.team:
            index = self.team_combo.findData(form.team)
            if index >= 0:
                self.team_combo.setCurrentIndex(index)
            else:
                self.team_combo.setCurrentText(form.team)

        if form.milestone_key:
            index = self.milestone_combo.findData(form.milestone_key)
            if index < 0:
                self.milestone_combo.addItem(
                    milestone.label if milestone is not None else form.milestone_key,
                    form.milestone_key,
                )
                index = self.milestone_combo.count() - 1
            self.milestone_combo.setCurrentIndex(index)

        self.value_combo.setCurrentText(_format_achieved_value(form.achieved_value))
        self.season_edit.setText(str(form.season) if form.season is not None else "")
        self.games_edit.setText(
            str(form.games_at_achievement) if form.games_at_achievement is not None else ""
        )
        if form.opponent_team:
            self.opponent_team_edit.setCurrentText(form.opponent_team)
        if form.opponent_player:
            self.opponent_player_edit.setCurrentText(form.opponent_player)
        self.description_edit.setText(form.description or "")
        self.notes_edit.setText(form.notes or "")

    def _player_display_name(self, player_id: int) -> str:
        if self.aggregator is None:
            return str(player_id)
        row = self.aggregator.conn.execute(
            "SELECT full_name, short_name FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if row:
            return str(row["full_name"] or row["short_name"] or player_id)
        return str(player_id)

    def _build(self) -> tuple[ManualMilestoneFormData, MilestoneDefinition | None, list[str]]:
        errors: list[str] = []
        achieved_date = _qdate_to_date(self.date_edit.date())
        if achieved_date is None:
            errors.append(tr("Check date format"))
            achieved_date = date.today()
        milestone = self._selected_milestone()
        raw_milestone_key = str(
            self.milestone_combo.currentData() or self.milestone_combo.currentText().strip()
        )
        if milestone is None and not raw_milestone_key:
            errors.append(tr("Please select a milestone."))

        value_text = self.value_combo.currentText().strip()
        achieved_value = 0.0
        if not value_text:
            errors.append(tr("Achieved value must be a number."))
        else:
            try:
                achieved_value = float(value_text)
            except ValueError:
                errors.append(tr("Achieved value must be a number."))

        season_text = self.season_edit.text().strip()
        season: int | None = achieved_date.year
        if season_text:
            try:
                season = int(season_text)
            except ValueError:
                errors.append(tr("Season must be a number."))
                season = achieved_date.year

        games_at: int | None = None
        scope = milestone.scope if milestone is not None else None
        if scope is not None and scope_needs_games_at_achievement(scope):
            text = self.games_edit.text().strip()
            if text:
                try:
                    games_at = int(text)
                except ValueError:
                    errors.append(tr("Games must be an integer."))
            elif self._category != "award":
                errors.append(tr("Games must be an integer."))

        is_player = self.player_radio.isChecked()
        player_id: int | None = None
        team: str | None = None
        if is_player:
            if self.aggregator is not None:
                player_id = ensure_player_id_from_combo(self.player_combo, self.aggregator)
            else:
                player_id = _optional_int(self.player_combo.currentText())
            team = first_tracked_team_name(self.settings) if self.settings is not None else None
        else:
            data = self.team_combo.currentData()
            team = str(data) if data else (self.team_combo.currentText().strip() or None)

        form = ManualMilestoneFormData(
            target="player" if is_player else "team",
            achieved_date=achieved_date,
            player_id=player_id,
            team=team,
            milestone_key=milestone.key if milestone is not None else raw_milestone_key,
            season=season,
            achieved_value=achieved_value,
            games_at_achievement=games_at,
            opponent_team=self.opponent_team_edit.currentText().strip(),
            opponent_player=canonical_player_text(self.opponent_player_edit),
            description=self.description_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )
        if self.milestones is not None or milestone is not None:
            errors.extend(validate_manual_entry(form, milestone))
        elif form.target == "player" and not form.player_id:
            errors.append(tr("Please select a player."))
        elif form.target == "team" and not (form.team or "").strip():
            errors.append(tr("Please select a team."))
        return form, milestone, _dedupe(errors)

    def validate(self) -> list[str]:
        _, _, errors = self._build()
        return errors

    def build_form_data(self) -> ManualMilestoneFormData:
        form, _, errors = self._build()
        if errors:
            raise ValueError(" ".join(errors))
        return form

    def edited_values(self) -> dict[str, str]:
        target = "player" if self.player_radio.isChecked() else "team"
        player_data = self.player_combo.currentData()
        team_data = self.team_combo.currentData()
        milestone_data = self.milestone_combo.currentData()
        return {
            "target": target,
            "achieved_date": _qdate_value(self.date_edit),
            "player_id": str(player_data) if player_data is not None else self.player_combo.currentText().strip(),
            "team": str(team_data) if team_data else self.team_combo.currentText().strip(),
            "milestone_key": str(milestone_data) if milestone_data else self.milestone_combo.currentText().strip(),
            "season": self.season_edit.text().strip(),
            "achieved_value": self.value_combo.currentText().strip(),
            "games_at_achievement": self.games_edit.text().strip(),
            "opponent_team": self.opponent_team_edit.currentText().strip(),
            "opponent_player": (
                canonical_player_text(self.opponent_player_edit)
                if self.aggregator is not None
                else self.opponent_player_edit.currentText().strip()
            ),
            "description": self.description_edit.text().strip(),
            "notes": self.notes_edit.text().strip(),
        }


class _TransferPage(QWidget):
    """Typed team-move/contract editor page."""

    def __init__(self, aggregator: Any, settings: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self._desc_auto = True

        layout = QVBoxLayout(self)
        hint = QLabel(
            tr(
                "Records player transfer events such as contracts and trades. "
                "Separate multiple players with commas."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(hint_style())

        self.date_edit = QDateEdit()
        _configure_date_edit(self.date_edit)

        self.joining_combo = QComboBox()
        self.leaving_combo = QComboBox()
        if aggregator is not None and settings is not None:
            configure_player_multipick_combo(self.joining_combo, aggregator, settings, self._update_description)
            configure_player_multipick_combo(self.leaving_combo, aggregator, settings, self._update_description)
        else:
            self.joining_combo.setEditable(True)
            self.leaving_combo.setEditable(True)
        self.joining_combo.lineEdit().textChanged.connect(self._update_description)
        self.leaving_combo.lineEdit().textChanged.connect(self._update_description)

        self.type_combo = QComboBox()
        for key, label in TRANSFER_EVENT_LABELS.items():
            self.type_combo.addItem(tr(label), key)
        self.type_combo.currentIndexChanged.connect(self._update_description)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.join_team_combo = QComboBox()
        self.counterpart_team_combo = QComboBox()
        if settings is not None:
            configure_mlb_team_combo(self.join_team_combo, settings, tracked_first=True)
            configure_mlb_team_combo(self.counterpart_team_combo, settings)
        else:
            self.join_team_combo.setEditable(True)
            self.counterpart_team_combo.setEditable(True)

        self.season_edit = QLineEdit()
        self.season_edit.setPlaceholderText(tr("Auto in-season"))
        self.description_edit = QLineEdit()
        self.description_edit.textEdited.connect(self._on_description_edited)
        self.notes_edit = QLineEdit()

        form_layout = QFormLayout()
        form_layout.addRow(_required_label(tr("Date:")), self.date_edit)
        form_layout.addRow(tr("Joining:"), self.joining_combo)
        form_layout.addRow(tr("Leaving:"), self.leaving_combo)
        form_layout.addRow(_required_label(tr("Type:")), self.type_combo)
        form_layout.addRow(_required_label(tr("Join Team:")), self.join_team_combo)
        form_layout.addRow(tr("Counterpart Team:"), self.counterpart_team_combo)
        form_layout.addRow(tr("Season:"), self.season_edit)
        form_layout.addRow(tr("Description:"), self.description_edit)
        form_layout.addRow(tr("Notes:"), self.notes_edit)

        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addStretch()

        self._on_type_changed()

    def _update_description(self) -> None:
        if str(self.type_combo.currentData()) != "trade" or not self._desc_auto:
            return
        joining = parse_player_name_list(self.joining_combo.currentText().strip())
        leaving = parse_player_name_list(self.leaving_combo.currentText().strip())
        self.description_edit.blockSignals(True)
        self.description_edit.setText(build_trade_description(joining, leaving))
        self.description_edit.blockSignals(False)

    def _on_description_edited(self, _text: str) -> None:
        joining = parse_player_name_list(self.joining_combo.currentText().strip())
        leaving = parse_player_name_list(self.leaving_combo.currentText().strip())
        auto = build_trade_description(joining, leaving)
        if self.description_edit.text().strip() != auto.strip():
            self._desc_auto = False

    def _on_type_changed(self) -> None:
        if str(self.type_combo.currentData()) != "fa_contract":
            return
        if self.join_team_combo.currentText().strip():
            return
        if self.settings is not None:
            tracked = tracked_team_names(self.settings)
            if tracked:
                self.join_team_combo.setEditText(tracked[0])

    def set_form(self, form: ManualTransferFormData) -> None:
        self.date_edit.setDate(_date_to_qdate(form.achieved_date))
        self.joining_combo.setCurrentText(form.joining_players)
        self.leaving_combo.setCurrentText(form.leaving_players)
        index = self.type_combo.findData(form.event_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        if form.join_team:
            self.join_team_combo.setCurrentText(form.join_team)
        if form.counterpart_team:
            self.counterpart_team_combo.setCurrentText(form.counterpart_team)
        self.season_edit.setText(str(form.season) if form.season is not None else "")
        self.description_edit.setText(form.description or "")
        self._desc_auto = not bool(form.description)
        self.notes_edit.setText(form.notes or "")

    def _build(self) -> tuple[ManualTransferFormData, list[str]]:
        errors: list[str] = []
        achieved_date = _qdate_to_date(self.date_edit.date())
        if achieved_date is None:
            errors.append(tr("Check date format"))
            achieved_date = date.today()

        season_text = self.season_edit.text().strip()
        season: int | None = None
        if season_text:
            try:
                season = int(season_text)
            except ValueError:
                errors.append(tr("Season must be a number."))
        else:
            season = (
                season_if_in_season(self.aggregator.conn, achieved_date)
                if self.aggregator is not None
                else achieved_date.year
            )
            if season is None:
                errors.append(tr("Off-season transfer: please enter the season directly."))

        event_type = str(self.type_combo.currentData())
        join_team = self.join_team_combo.currentText().strip()
        if not join_team and event_type == "fa_contract":
            if self.settings is not None:
                tracked = tracked_team_names(self.settings)
                if tracked:
                    join_team = tracked[0]

        form = ManualTransferFormData(
            achieved_date=achieved_date,
            joining_players=self.joining_combo.currentText().strip(),
            leaving_players=self.leaving_combo.currentText().strip(),
            event_type=event_type,
            join_team=join_team,
            counterpart_team=self.counterpart_team_combo.currentText().strip(),
            season=season,
            description=self.description_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )
        errors.extend(validate_manual_transfer(form))
        return form, _dedupe(errors)

    def validate(self) -> list[str]:
        _, errors = self._build()
        return errors

    def build_form_data(self) -> ManualTransferFormData:
        form, errors = self._build()
        if errors:
            raise ValueError(" ".join(errors))
        return form

    def edited_values(self) -> dict[str, str]:
        return {
            "achieved_date": _qdate_value(self.date_edit),
            "joining_players": self.joining_combo.currentText().strip(),
            "leaving_players": self.leaving_combo.currentText().strip(),
            "event_type": str(self.type_combo.currentData() or self.type_combo.currentText().strip()),
            "join_team": self.join_team_combo.currentText().strip(),
            "counterpart_team": self.counterpart_team_combo.currentText().strip(),
            "season": self.season_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "notes": self.notes_edit.text().strip(),
            "fa_is_retention": "",
        }


class _InjuryPage(QWidget):
    """Typed injury editor page."""

    def __init__(self, aggregator: Any, settings: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings

        layout = QVBoxLayout(self)
        hint = QLabel(tr("Records injury events such as player injuries and returns."))
        hint.setWordWrap(True)
        hint.setStyleSheet(hint_style())

        self.date_edit = QDateEdit()
        _configure_date_edit(self.date_edit)

        self.player_combo = QComboBox()
        if aggregator is not None and settings is not None:
            configure_player_combo(self.player_combo, aggregator, settings)
        else:
            self.player_combo.setEditable(True)

        self.injury_label_edit = QLineEdit()
        self.injury_label_edit.setPlaceholderText(tr("e.g., Hamstring, shoulder surgery"))
        self.duration_edit = QLineEdit()
        self.duration_edit.setPlaceholderText(tr("e.g., 3 days, 3 weeks, 5-6 months"))
        self.team_combo = QComboBox()
        if settings is not None:
            configure_tracked_team_combo(self.team_combo, settings)
        else:
            self.team_combo.setEditable(True)
        self.season_edit = QLineEdit()
        self.season_edit.setPlaceholderText(tr("Auto (date year)"))
        self.description_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        self.injury_label_edit.textChanged.connect(self._update_description)
        self.duration_edit.textChanged.connect(self._update_description)

        form_layout = QFormLayout()
        form_layout.addRow(_required_label(tr("Date:")), self.date_edit)
        form_layout.addRow(_required_label(tr("Player:")), self.player_combo)
        form_layout.addRow(_required_label(tr("Injury:")), self.injury_label_edit)
        form_layout.addRow(tr("Duration:"), self.duration_edit)
        form_layout.addRow(tr("Affil. Team:"), self.team_combo)
        form_layout.addRow(tr("Season:"), self.season_edit)
        form_layout.addRow(tr("Description:"), self.description_edit)
        form_layout.addRow(tr("Notes:"), self.notes_edit)

        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addStretch()

    def _update_description(self) -> None:
        self.description_edit.setText(
            build_injury_description(self.injury_label_edit.text(), self.duration_edit.text())
        )

    def set_form(self, form: ManualInjuryFormData) -> None:
        self.date_edit.setDate(_date_to_qdate(form.achieved_date))
        if form.player_name:
            self.player_combo.setCurrentText(form.player_name)
        self.injury_label_edit.setText(form.injury_label or "")
        self.duration_edit.setText(form.duration or "")
        if form.team:
            index = self.team_combo.findData(form.team)
            if index >= 0:
                self.team_combo.setCurrentIndex(index)
            else:
                self.team_combo.setCurrentText(form.team)
        self.season_edit.setText(str(form.season) if form.season is not None else "")
        self.description_edit.setText(form.description or "")
        self.notes_edit.setText(form.notes or "")

    def _build(self) -> tuple[ManualInjuryFormData, list[str]]:
        errors: list[str] = []
        achieved_date = _qdate_to_date(self.date_edit.date())
        if achieved_date is None:
            errors.append(tr("Check date format"))
            achieved_date = date.today()

        season_text = self.season_edit.text().strip()
        season: int | None = achieved_date.year
        if season_text:
            try:
                season = int(season_text)
            except ValueError:
                errors.append(tr("Season must be a number."))
                season = achieved_date.year

        team = self.team_combo.currentText().strip()
        if not team and self.settings is not None:
            team = first_tracked_team_name(self.settings)

        form = ManualInjuryFormData(
            player_name=(
                canonical_player_text(self.player_combo)
                if self.aggregator is not None
                else self.player_combo.currentText().strip()
            ),
            achieved_date=achieved_date,
            injury_label=self.injury_label_edit.text().strip(),
            duration=self.duration_edit.text().strip(),
            team=team,
            season=season,
            description=self.description_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )
        errors.extend(validate_manual_injury(form))
        return form, _dedupe(errors)

    def validate(self) -> list[str]:
        _, errors = self._build()
        return errors

    def build_form_data(self) -> ManualInjuryFormData:
        form, errors = self._build()
        if errors:
            raise ValueError(" ".join(errors))
        return form

    def edited_values(self) -> dict[str, str]:
        return {
            "player_name": (
                canonical_player_text(self.player_combo)
                if self.aggregator is not None
                else self.player_combo.currentText().strip()
            ),
            "achieved_date": _qdate_value(self.date_edit),
            "injury_label": self.injury_label_edit.text().strip(),
            "duration": self.duration_edit.text().strip(),
            "team": self.team_combo.currentText().strip(),
            "season": self.season_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "notes": self.notes_edit.text().strip(),
        }


class GuidedRecordEditor(QWidget):
    """Typed, validated single-record editor shared by manual entry and
    message-review corrections.

    Presents one of three typed pages (milestone/award, transfer/contract,
    injury) depending on the record being edited, built from the same
    widgets (``QDateEdit`` with a calendar popup, player/team autocomplete
    combos) and the same ``validate_manual_*`` functions used everywhere
    else in the app.
    """

    def __init__(
        self,
        aggregator: Any | None = None,
        settings: Any | None = None,
        milestones: MilestoneDefinitions | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.milestones = milestones

        self._milestone_page = _MilestoneAwardPage(aggregator, settings, milestones, parent=self)
        self._transfer_page = _TransferPage(aggregator, settings, parent=self)
        self._injury_page = _InjuryPage(aggregator, settings, parent=self)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._milestone_page)
        self._stack.addWidget(self._transfer_page)
        self._stack.addWidget(self._injury_page)
        self._active_page: QWidget = self._milestone_page

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    def set_category(self, category: Literal["milestone", "award"]) -> None:
        self._milestone_page.set_category(category)

    def set_record_type(self, record_type: Literal["milestone", "transfer", "injury"]) -> None:
        page = {
            "milestone": self._milestone_page,
            "transfer": self._transfer_page,
            "injury": self._injury_page,
        }[record_type]
        self._stack.setCurrentWidget(page)
        self._active_page = page

    def set_form(self, form: Any) -> None:
        if isinstance(form, ManualTransferFormData):
            self.set_record_type("transfer")
        elif isinstance(form, ManualInjuryFormData):
            self.set_record_type("injury")
        elif isinstance(form, ManualMilestoneFormData):
            self.set_record_type("milestone")
        else:
            raise TypeError(f"Unsupported guided record form: {type(form)!r}")
        self._active_page.set_form(form)

    def build_form_data(self) -> Any:
        return self._active_page.build_form_data()

    def validate(self) -> list[str]:
        return self._active_page.validate()

    def edited_values(self) -> dict[str, str]:
        return self._active_page.edited_values()

    def set_initial_date(self, value: date) -> None:
        """Pre-fill the active page's date field (e.g. from a shared bulk-entry date)."""
        self._active_page.date_edit.setDate(_date_to_qdate(value))

    def selected_milestone(self) -> MilestoneDefinition | None:
        if self._active_page is self._milestone_page:
            return self._milestone_page.selected_milestone()
        return None

    def set_source_fields_read_only(self, read_only: bool = True) -> None:
        """Protect extraction provenance while leaving manual notes editable."""

        for page in (
            self._milestone_page,
            self._transfer_page,
            self._injury_page,
        ):
            page.notes_edit.setReadOnly(read_only)


class GuidedMilestoneForm(QWidget):
    """Field editor used by message-review corrections.

    Kept as a thin, backward-compatible wrapper: existing callers construct
    it as ``GuidedMilestoneForm(forms, parent=...)``. The visible editor is
    always the typed ``GuidedRecordEditor``; a hidden table is maintained only
    for older tests/callers that inspect translated labels directly.
    """

    def __init__(
        self,
        forms: Iterable[Any] = (),
        *,
        intro: str | None = None,
        parent: QWidget | None = None,
        aggregator: Any | None = None,
        settings: Any | None = None,
        milestones: MilestoneDefinitions | None = None,
    ) -> None:
        super().__init__(parent)
        self._forms: list[Any] = []

        layout = QVBoxLayout(self)
        self.hint_label = QLabel(intro or tr("Review and correct only the fields needed for this record."))
        self.hint_label.setObjectName("mutedLabel")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.form_combo = QComboBox()
        self.form_combo.currentIndexChanged.connect(self._load_selected_form)
        layout.addWidget(self.form_combo)

        self.source_id_label = QLabel()
        self.source_id_label.setObjectName("guidedRecordSourceId")
        self.source_id_label.setWordWrap(True)
        layout.addWidget(self.source_id_label)

        self.editor = GuidedRecordEditor(aggregator, settings, milestones, parent=self)
        self.editor.set_source_fields_read_only(True)
        layout.addWidget(self.editor, stretch=1)

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("guidedMilestoneFormTable")
        self.table.setHorizontalHeaderLabels([tr("Field"), tr("Value")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.hide()

        self.set_forms(forms)

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

    def validate(self) -> list[str]:
        return self.editor.validate()

    def build_form_data(self) -> Any:
        return self.editor.build_form_data()

    def edited_values(self) -> dict[str, str]:
        return self.editor.edited_values()

    def _load_selected_form(self) -> None:
        index = self.selected_form_index()
        if not (0 <= index < len(self._forms)):
            self.table.setRowCount(0)
            return
        form = self._forms[index]

        self.editor.set_form(form)
        source_id = str(getattr(form, "notes", "") or "").strip()
        self.source_id_label.setText(
            tr("Original message ID") + f": {source_id}"
            if source_id
            else tr("Original message ID") + ": -"
        )
        values = editable_field_values(form)
        self.table.setRowCount(len(values))
        for row, (key, value) in enumerate(values.items()):
            label_item = QTableWidgetItem(display_field(key))
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, label_item)
            self.table.setItem(row, 1, QTableWidgetItem(value))
