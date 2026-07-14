""""Enter one at a time" popup dialogs for manual milestone/award/transfer/injury entry.

These mirror the classic single-record form and are opened from
ManualMilestoneDialog's "Add One at a Time" button. On accept, the built
form dataclass is available on `.form` (and `.milestone` for milestone/award).
"""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.implementation import manual_entry_hint, requires_external_data
from core.milestone.manual_entry import (
    ManualEntryCategory,
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    TRANSFER_EVENT_LABELS,
    build_injury_description,
    build_trade_description,
    check_duplicate,
    get_achieved_value_candidates,
    milestones_for_manual_entry,
    parse_flexible_date,
    parse_player_name_list,
    scope_needs_games_at_achievement,
    scope_needs_season,
    validate_manual_entry,
    validate_manual_injury,
    validate_manual_transfer,
)
from core.roster.player_registry import PlayerRegistry
from core.stats.aggregator import Aggregator
from gui.ui_compact import hint_style, scale_size
from gui.widgets.app_dialog import add_dialog_footer, error_label, init_dialog_layout, make_button_box
from gui.widgets.manual_entry_fields import (
    apply_completer,
    canonical_player_text,
    configure_mlb_team_combo,
    configure_player_combo,
    configure_player_multipick_combo,
    configure_tracked_team_combo,
    ensure_player_id_from_combo,
    fill_mlb_team_combo,
    fill_tracked_team_combo,
    tracked_team_names,
)


class SingleMilestoneEntryDialog(QDialog):
    """One-at-a-time entry for a milestone or award record."""

    def __init__(
        self,
        category: Literal["milestone", "award"],
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.category: Literal["milestone", "award"] = category
        self.form: ManualMilestoneFormData | None = None
        self.milestone: MilestoneDefinition | None = None
        self.setWindowTitle(tr("Add Award") if category == "award" else tr("Add Milestone"))
        self.resize(*scale_size(520, 560))

        page = QWidget()
        layout = QVBoxLayout(page)

        self.player_radio = QRadioButton(tr("Personal"))
        self.team_radio = QRadioButton(tr("Team"))
        self.player_radio.setChecked(True)
        self.player_radio.toggled.connect(self._on_target_changed)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel(tr("Target:")))
        target_row.addWidget(self.player_radio)
        target_row.addWidget(self.team_radio)
        target_row.addStretch()

        self.date_edit = QLineEdit(initial_date)
        self.date_edit.setPlaceholderText("2026-03-01")
        self.date_error = error_label()
        self.date_error.hide()
        self.date_edit.textChanged.connect(self._validate_date_field)

        self.player_combo = QComboBox()
        configure_player_combo(self.player_combo, aggregator, settings)
        line = self.player_combo.lineEdit()
        if line is not None:
            line.setPlaceholderText(
                tr("Enter full name or select from list (e.g., Dong-ju Moon)")
            )
        self.add_player_button = QPushButton(tr("+ Add Player"))
        self.add_player_button.clicked.connect(self._on_add_player)

        player_row = QHBoxLayout()
        player_row.addWidget(self.player_combo, stretch=1)
        player_row.addWidget(self.add_player_button)
        self.player_row_widget = QWidget()
        self.player_row_widget.setLayout(player_row)

        self.team_combo = QComboBox()
        fill_tracked_team_combo(self.team_combo, settings)
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

        self.season_edit = QLineEdit(str(settings.current_season))
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
        configure_mlb_team_combo(self.opponent_team_edit, settings)

        self.opponent_player_edit = QComboBox()
        configure_player_combo(self.opponent_player_edit, aggregator, settings)

        self.description_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        self.form_layout = QFormLayout()
        self.form_layout.addRow(tr("Date:"), self.date_edit)
        self.form_layout.addRow("", self.date_error)
        self.form_layout.addRow(tr("Player:"), self.player_row_widget)
        self.form_layout.addRow(tr("Team:"), self.team_row_widget)
        self.form_layout.addRow(tr("Milestone:"), self.milestone_combo)
        self.form_layout.addRow(self.season_label, self.season_row_widget)
        self.form_layout.addRow(self.games_label, self.games_row_widget)
        self.form_layout.addRow(tr("Achieved Value:"), self.value_combo)
        self.form_layout.addRow(tr("Opponent:"), self.opponent_team_edit)
        self.form_layout.addRow(tr("Opp. Player:"), self.opponent_player_edit)
        self.form_layout.addRow(tr("Description:"), self.description_edit)
        self.form_layout.addRow(tr("Notes:"), self.notes_edit)
        self.form_layout.setRowVisible(self.opponent_player_edit, category != "award")

        layout.addLayout(target_row)
        layout.addWidget(self.manual_hint)
        layout.addLayout(self.form_layout)
        layout.addStretch()

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(page, stretch=1)
        add_dialog_footer(outer, buttons)

        self._reload_milestones()
        self._on_target_changed()

    def _player_registry(self) -> PlayerRegistry:
        return PlayerRegistry(self.aggregator)

    def _reload_milestones(self) -> None:
        target = "player" if self.player_radio.isChecked() else "team"
        pool = milestones_for_manual_entry(
            self.milestones.all_milestones, target, category=self.category
        )
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

    def _on_target_changed(self) -> None:
        is_player = self.player_radio.isChecked()
        self.player_row_widget.setVisible(is_player)
        self.team_row_widget.setVisible(not is_player)
        self._reload_milestones()

    def _selected_milestone(self) -> MilestoneDefinition | None:
        key = self.milestone_combo.currentData()
        if not key:
            return None
        return self.milestones.get_by_key(str(key))

    def _update_milestone_hint(self) -> None:
        if self.category == "award":
            self.manual_hint.setText(
                tr("Awards, league leaders, and other items not auto-detected from boxscores.")
            )
            milestone = self._selected_milestone()
            if milestone is not None:
                self.manual_hint.setText(manual_entry_hint(milestone))
            return
        milestone = self._selected_milestone()
        if milestone is not None and requires_external_data(milestone):
            self.manual_hint.setText(manual_entry_hint(milestone))
        else:
            self.manual_hint.setText(
                tr("Can be auto-detected from boxscores, but use this to supplement or correct.")
            )

    def _on_milestone_changed(self) -> None:
        milestone = self._selected_milestone()
        if milestone is None:
            return
        self._update_milestone_hint()
        scope = milestone.scope
        self.season_row_widget.setVisible(scope_needs_season(scope))
        self.season_label.setVisible(scope_needs_season(scope))
        self.games_row_widget.setVisible(scope_needs_games_at_achievement(scope))
        self.games_label.setVisible(scope_needs_games_at_achievement(scope))

        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        for candidate in get_achieved_value_candidates(milestone):
            self.value_combo.addItem(candidate)
        if self.value_combo.count():
            self.value_combo.setCurrentIndex(0)
        self.value_combo.blockSignals(False)

    def _validate_date_field(self) -> None:
        text = self.date_edit.text().strip()
        if not text:
            self.date_error.hide()
            return
        if parse_flexible_date(text) is None:
            self.date_error.setText(tr("Check date format"))
            self.date_error.show()
        else:
            self.date_error.hide()

    def _on_add_player(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("Add Player"), tr("Enter full name (e.g., Dong-ju Moon):")
        )
        if not ok:
            return
        try:
            player_id = self._player_registry().add_manual_player(name)
        except ValueError as exc:
            QMessageBox.warning(self, tr("Input Error"), str(exc))
            return
        for combo in (self.player_combo, self.opponent_player_edit):
            configure_player_combo(combo, self.aggregator, self.settings)
        index = self.player_combo.findData(player_id)
        if index >= 0:
            self.player_combo.setCurrentIndex(index)

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _on_accept(self) -> None:
        parsed = parse_flexible_date(self.date_edit.text())
        if parsed is None:
            self.date_error.setText(tr("Check date format"))
            self.date_error.show()
            return

        milestone = self._selected_milestone()
        if milestone is None:
            QMessageBox.warning(self, tr("Input Required"), tr("Please select a milestone."))
            return

        try:
            achieved_value = float(self.value_combo.currentText().strip())
        except ValueError:
            QMessageBox.warning(self, tr("Input Error"), tr("Achieved value must be a number."))
            return

        season: int | None = None
        if scope_needs_season(milestone.scope):
            try:
                season = int(self.season_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
                return

        games_at: int | None = None
        if scope_needs_games_at_achievement(milestone.scope):
            text = self.games_edit.text().strip()
            if text:
                try:
                    games_at = int(text)
                except ValueError:
                    QMessageBox.warning(self, tr("Input Error"), tr("Games must be an integer."))
                    return
            elif self.category != "award":
                QMessageBox.warning(self, tr("Input Error"), tr("Games must be an integer."))
                return

        is_player = self.player_radio.isChecked()
        player_id: int | None = None
        if is_player:
            player_id = ensure_player_id_from_combo(self.player_combo, self.aggregator)
            if player_id is None:
                QMessageBox.warning(
                    self, tr("Input Required"), tr("Select a player or enter a full name.")
                )
                return
        team = self.team_combo.currentData() if not is_player else None

        form = ManualMilestoneFormData(
            target="player" if is_player else "team",
            achieved_date=parsed,
            player_id=player_id,
            team=str(team) if team else None,
            milestone_key=milestone.key,
            season=season,
            achieved_value=achieved_value,
            games_at_achievement=games_at,
            opponent_team=self._combo_text(self.opponent_team_edit),
            opponent_player=canonical_player_text(self.opponent_player_edit),
            description=self.description_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )
        errors = validate_manual_entry(form, milestone)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return

        dup_kind, dup_msg = check_duplicate(self.aggregator.conn, form, milestone)
        if dup_kind == "warn":
            reply = QMessageBox.question(
                self,
                tr("Duplicate Check"),
                tr("{dup_msg}\nAdd anyway?").format(dup_msg=dup_msg),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.form = form
        self.milestone = milestone
        self.accept()


class SingleTransferEntryDialog(QDialog):
    """One-at-a-time entry for a player transfer/contract event."""

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.form: ManualTransferFormData | None = None
        self.setWindowTitle(tr("Add Team Move"))
        self.resize(*scale_size(520, 480))
        self._transfer_desc_auto = True

        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            tr(
                "Records player transfer events such as contracts and trades. "
                "Separate multiple players with commas."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(hint_style())

        self.transfer_date_edit = QLineEdit(initial_date)
        self.transfer_date_edit.setPlaceholderText("2026-03-01")
        self.transfer_date_error = error_label()
        self.transfer_date_error.hide()
        self.transfer_date_edit.textChanged.connect(self._validate_date_field)

        self.transfer_joining_combo = QComboBox()
        self.transfer_leaving_combo = QComboBox()
        configure_player_multipick_combo(
            self.transfer_joining_combo, aggregator, settings, self._update_transfer_description
        )
        configure_player_multipick_combo(
            self.transfer_leaving_combo, aggregator, settings, self._update_transfer_description
        )

        self.transfer_type_combo = QComboBox()
        for key, label in TRANSFER_EVENT_LABELS.items():
            self.transfer_type_combo.addItem(tr(label), key)
        self.transfer_type_combo.currentIndexChanged.connect(self._update_transfer_description)
        self.transfer_type_combo.currentIndexChanged.connect(self._on_transfer_type_changed)

        self.transfer_join_team_combo = QComboBox()
        self.transfer_counterpart_team_combo = QComboBox()
        configure_mlb_team_combo(self.transfer_join_team_combo, settings, tracked_first=True)
        configure_mlb_team_combo(self.transfer_counterpart_team_combo, settings)
        self.transfer_season_edit = QLineEdit(str(settings.current_season))
        self.transfer_description_edit = QLineEdit()
        self.transfer_description_edit.textEdited.connect(self._on_transfer_description_edited)
        self.transfer_notes_edit = QLineEdit()

        self.transfer_joining_combo.lineEdit().textChanged.connect(
            self._update_transfer_description
        )
        self.transfer_leaving_combo.lineEdit().textChanged.connect(
            self._update_transfer_description
        )

        form_layout = QFormLayout()
        form_layout.addRow(tr("Date:"), self.transfer_date_edit)
        form_layout.addRow("", self.transfer_date_error)
        form_layout.addRow(tr("Joining:"), self.transfer_joining_combo)
        form_layout.addRow(tr("Leaving:"), self.transfer_leaving_combo)
        form_layout.addRow(tr("Type:"), self.transfer_type_combo)
        form_layout.addRow(tr("Join Team:"), self.transfer_join_team_combo)
        form_layout.addRow(tr("Counterpart Team:"), self.transfer_counterpart_team_combo)
        form_layout.addRow(tr("Season:"), self.transfer_season_edit)
        form_layout.addRow(tr("Description:"), self.transfer_description_edit)
        form_layout.addRow(tr("Notes:"), self.transfer_notes_edit)

        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addStretch()

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(page, stretch=1)
        add_dialog_footer(outer, buttons)

        self._on_transfer_type_changed()

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _validate_date_field(self) -> None:
        text = self.transfer_date_edit.text().strip()
        if not text:
            self.transfer_date_error.hide()
            return
        if parse_flexible_date(text) is None:
            self.transfer_date_error.setText(tr("Check date format"))
            self.transfer_date_error.show()
        else:
            self.transfer_date_error.hide()

    def _on_transfer_type_changed(self) -> None:
        if str(self.transfer_type_combo.currentData()) != "fa_contract":
            return
        if self.transfer_join_team_combo.currentText().strip():
            return
        tracked = tracked_team_names(self.settings)
        if tracked:
            self.transfer_join_team_combo.setEditText(tracked[0])

    def _update_transfer_description(self) -> None:
        if str(self.transfer_type_combo.currentData()) != "trade":
            return
        if not self._transfer_desc_auto:
            return
        joining = parse_player_name_list(self._combo_text(self.transfer_joining_combo))
        leaving = parse_player_name_list(self._combo_text(self.transfer_leaving_combo))
        self.transfer_description_edit.blockSignals(True)
        self.transfer_description_edit.setText(build_trade_description(joining, leaving))
        self.transfer_description_edit.blockSignals(False)

    def _on_transfer_description_edited(self, _text: str) -> None:
        joining = parse_player_name_list(self._combo_text(self.transfer_joining_combo))
        leaving = parse_player_name_list(self._combo_text(self.transfer_leaving_combo))
        auto = build_trade_description(joining, leaving)
        if self.transfer_description_edit.text().strip() != auto.strip():
            self._transfer_desc_auto = False

    def _parse_optional_season(self, text: str) -> int | None:
        raw = text.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _on_accept(self) -> None:
        parsed = parse_flexible_date(self.transfer_date_edit.text())
        if parsed is None:
            self.transfer_date_error.setText(tr("Check date format"))
            self.transfer_date_error.show()
            return

        season = self._parse_optional_season(self.transfer_season_edit.text())
        if self.transfer_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
            return

        join_team = self._combo_text(self.transfer_join_team_combo)
        if not join_team and str(self.transfer_type_combo.currentData()) == "fa_contract":
            tracked = tracked_team_names(self.settings)
            if tracked:
                join_team = tracked[0]

        form = ManualTransferFormData(
            achieved_date=parsed,
            joining_players=self._combo_text(self.transfer_joining_combo),
            leaving_players=self._combo_text(self.transfer_leaving_combo),
            event_type=str(self.transfer_type_combo.currentData()),
            join_team=join_team,
            counterpart_team=self._combo_text(self.transfer_counterpart_team_combo),
            season=season,
            description=self.transfer_description_edit.text().strip(),
            notes=self.transfer_notes_edit.text().strip(),
        )
        errors = validate_manual_transfer(form)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return

        self.form = form
        self.accept()


class SingleInjuryEntryDialog(QDialog):
    """One-at-a-time entry for a player injury/return event."""

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.form: ManualInjuryFormData | None = None
        self.setWindowTitle(tr("Add Injury"))
        self.resize(*scale_size(480, 420))

        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(tr("Records injury events such as player injuries and returns."))
        hint.setWordWrap(True)
        hint.setStyleSheet(hint_style())

        self.injury_date_edit = QLineEdit(initial_date)
        self.injury_date_edit.setPlaceholderText("2026-03-01")
        self.injury_date_error = error_label()
        self.injury_date_error.hide()
        self.injury_date_edit.textChanged.connect(self._validate_date_field)

        self.injury_player_combo = QComboBox()
        configure_player_combo(self.injury_player_combo, aggregator, settings)

        self.injury_label_edit = QLineEdit()
        self.injury_label_edit.setPlaceholderText(tr("e.g., Hamstring, shoulder surgery"))
        self.injury_duration_edit = QLineEdit()
        self.injury_duration_edit.setPlaceholderText(tr("e.g., 3 days, 3 weeks, 5-6 months"))
        self.injury_team_combo = QComboBox()
        configure_tracked_team_combo(self.injury_team_combo, settings)
        self.injury_season_edit = QLineEdit(str(settings.current_season))
        self.injury_description_edit = QLineEdit()
        self.injury_notes_edit = QLineEdit()

        self.injury_label_edit.textChanged.connect(self._update_injury_description)
        self.injury_duration_edit.textChanged.connect(self._update_injury_description)

        form_layout = QFormLayout()
        form_layout.addRow(tr("Date:"), self.injury_date_edit)
        form_layout.addRow("", self.injury_date_error)
        form_layout.addRow(tr("Player:"), self.injury_player_combo)
        form_layout.addRow(tr("Injury:"), self.injury_label_edit)
        form_layout.addRow(tr("Duration:"), self.injury_duration_edit)
        form_layout.addRow(tr("Affil. Team:"), self.injury_team_combo)
        form_layout.addRow(tr("Season:"), self.injury_season_edit)
        form_layout.addRow(tr("Description:"), self.injury_description_edit)
        form_layout.addRow(tr("Notes:"), self.injury_notes_edit)

        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addStretch()

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(page, stretch=1)
        add_dialog_footer(outer, buttons)

    def _validate_date_field(self) -> None:
        text = self.injury_date_edit.text().strip()
        if not text:
            self.injury_date_error.hide()
            return
        if parse_flexible_date(text) is None:
            self.injury_date_error.setText(tr("Check date format"))
            self.injury_date_error.show()
        else:
            self.injury_date_error.hide()

    def _update_injury_description(self) -> None:
        text = build_injury_description(
            self.injury_label_edit.text(), self.injury_duration_edit.text()
        )
        self.injury_description_edit.setText(text)

    def _parse_optional_season(self, text: str) -> int | None:
        raw = text.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _on_accept(self) -> None:
        parsed = parse_flexible_date(self.injury_date_edit.text())
        if parsed is None:
            self.injury_date_error.setText(tr("Check date format"))
            self.injury_date_error.show()
            return

        season = self._parse_optional_season(self.injury_season_edit.text())
        if self.injury_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
            return

        form = ManualInjuryFormData(
            player_name=canonical_player_text(self.injury_player_combo),
            achieved_date=parsed,
            injury_label=self.injury_label_edit.text().strip(),
            duration=self.injury_duration_edit.text().strip(),
            team=self._combo_text(self.injury_team_combo),
            season=season,
            description=self.injury_description_edit.text().strip(),
            notes=self.injury_notes_edit.text().strip(),
        )
        errors = validate_manual_injury(form)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return

        self.form = form
        self.accept()

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()
