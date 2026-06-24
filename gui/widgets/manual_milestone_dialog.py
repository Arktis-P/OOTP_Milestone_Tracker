"""Unified manual milestone entry dialog with category tabs."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.milestone.checker import MilestoneChecker
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
from core.roster.korean_names import korean_display_for_player, load_korean_name_mapper, load_roster_player_names
from core.stats.player_display import format_manual_entry_label, format_player_list_label
from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    expand_tracked_teams,
    merge_team_maps,
)
from gui.ui_compact import hint_style, scale_size
from gui.widgets.app_dialog import add_dialog_footer, error_label, init_dialog_layout, make_button_box
from gui.widgets.card_panel import CardPanel

_TAB_MILESTONE = 0
_TAB_AWARD = 1
_TAB_TRANSFER = 2
_TAB_INJURY = 3


class ManualMilestoneDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        initial_tab: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.setWindowTitle(tr("Manual Entry"))
        self.resize(*scale_size(540, 560))

        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), tr("Milestone"))
        self.tabs.addTab(QWidget(), tr("Award"))
        self.tabs.addTab(QWidget(), tr("Transfer"))
        self.tabs.addTab(QWidget(), tr("Injury"))
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_milestone_page())
        self.stack.addWidget(self._build_transfer_page())
        self.stack.addWidget(self._build_injury_page())

        buttons = make_button_box(save=True, save_text="Add Record")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        content_card = CardPanel(tr("Manual Entry"))
        content_card.add_widget(self.tabs)
        content_card.add_widget(self.stack)

        layout = init_dialog_layout(self)
        layout.addWidget(content_card, stretch=1)
        add_dialog_footer(layout, buttons)

        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(initial_tab)
        self.tabs.blockSignals(False)
        self._on_tab_changed(initial_tab)

    def _build_milestone_page(self) -> QWidget:
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

        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("2026-03-01")
        self.date_error = error_label()
        self.date_error.hide()
        self.date_edit.textChanged.connect(self._validate_date_field)

        self.player_combo = QComboBox()
        self.player_combo.setEditable(True)
        self.player_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_players()
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
        self._fill_teams()
        self.team_row_widget = QWidget()
        team_layout = QHBoxLayout(self.team_row_widget)
        team_layout.setContentsMargins(0, 0, 0, 0)
        team_layout.addWidget(self.team_combo)

        self.milestone_combo = QComboBox()
        self.milestone_combo.setEditable(True)
        self.milestone_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.milestone_combo.currentIndexChanged.connect(self._on_milestone_changed)

        self.manual_hint = QLabel("")
        self.manual_hint.setWordWrap(True)
        self.manual_hint.setStyleSheet(hint_style())
        self.manual_hint.setText(
            tr(
                "Select tracked team players from the list, or enter a full name directly "
                "/ use '+ Add Player' to register players not yet in the DB."
            )
        )

        self.season_edit = QLineEdit(str(self.settings.current_season))
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

        self.opponent_team_edit = QLineEdit()
        self.opponent_player_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        self.form = QFormLayout()
        self.form.addRow(tr("Date:"), self.date_edit)
        self.form.addRow("", self.date_error)
        self.form.addRow(tr("Player:"), self.player_row_widget)
        self.form.addRow(tr("Team:"), self.team_row_widget)
        self.form.addRow(tr("Milestone:"), self.milestone_combo)
        self.form.addRow(self.season_label, self.season_row_widget)
        self.form.addRow(self.games_label, self.games_row_widget)
        self.form.addRow(tr("Achieved Value:"), self.value_combo)
        self.form.addRow(tr("Opponent:"), self.opponent_team_edit)
        self.form.addRow(tr("Opp. Player:"), self.opponent_player_edit)
        self.form.addRow(tr("Description:"), self.description_edit)
        self.form.addRow(tr("Notes:"), self.notes_edit)

        layout.addLayout(target_row)
        layout.addWidget(self.manual_hint)
        layout.addLayout(self.form)
        layout.addStretch()

        self._reload_milestones()
        self._on_target_changed()
        return page

    def _build_transfer_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.transfer_hint = QLabel(
            tr(
                "Records player transfer events such as contracts and trades. "
                "Separate multiple players with commas."
            )
        )
        self.transfer_hint.setWordWrap(True)
        self.transfer_hint.setStyleSheet(hint_style())

        self.transfer_date_edit = QLineEdit()
        self.transfer_date_edit.setPlaceholderText("2026-03-01")
        self.transfer_date_error = error_label()
        self.transfer_date_error.hide()
        self.transfer_date_edit.textChanged.connect(self._validate_transfer_date_field)

        self.transfer_joining_combo = QComboBox()
        self.transfer_leaving_combo = QComboBox()
        self._configure_player_multipick_combo(self.transfer_joining_combo)
        self._configure_player_multipick_combo(self.transfer_leaving_combo)

        self.transfer_type_combo = QComboBox()
        for key, label in TRANSFER_EVENT_LABELS.items():
            self.transfer_type_combo.addItem(tr(label), key)
        self.transfer_type_combo.currentIndexChanged.connect(
            self._update_transfer_description
        )

        self.transfer_join_team_combo = QComboBox()
        self.transfer_counterpart_team_combo = QComboBox()
        self._fill_mlb_team_combo(self.transfer_join_team_combo)
        self._fill_mlb_team_combo(self.transfer_counterpart_team_combo)
        self.transfer_season_edit = QLineEdit(str(self.settings.current_season))
        self.transfer_description_edit = QLineEdit()
        self.transfer_description_edit.textEdited.connect(
            self._on_transfer_description_edited
        )
        self.transfer_notes_edit = QLineEdit()
        self._transfer_desc_auto = True

        self.transfer_joining_combo.lineEdit().textChanged.connect(
            self._update_transfer_description
        )
        self.transfer_leaving_combo.lineEdit().textChanged.connect(
            self._update_transfer_description
        )

        transfer_form = QFormLayout()
        transfer_form.addRow(tr("Date:"), self.transfer_date_edit)
        transfer_form.addRow("", self.transfer_date_error)
        transfer_form.addRow(tr("Joining:"), self.transfer_joining_combo)
        transfer_form.addRow(tr("Leaving:"), self.transfer_leaving_combo)
        transfer_form.addRow(tr("Type:"), self.transfer_type_combo)
        transfer_form.addRow(tr("Join Team:"), self.transfer_join_team_combo)
        transfer_form.addRow(tr("Counterpart Team:"), self.transfer_counterpart_team_combo)
        transfer_form.addRow(tr("Season:"), self.transfer_season_edit)
        transfer_form.addRow(tr("Description:"), self.transfer_description_edit)
        transfer_form.addRow(tr("Notes:"), self.transfer_notes_edit)

        layout.addWidget(self.transfer_hint)
        layout.addLayout(transfer_form)
        layout.addStretch()
        return page

    def _build_injury_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.injury_hint = QLabel(
            tr("Records injury events such as player injuries and returns.")
        )
        self.injury_hint.setWordWrap(True)
        self.injury_hint.setStyleSheet(hint_style())

        self.injury_date_edit = QLineEdit()
        self.injury_date_edit.setPlaceholderText("2026-03-01")
        self.injury_date_error = error_label()
        self.injury_date_error.hide()
        self.injury_date_edit.textChanged.connect(self._validate_injury_date_field)

        self.injury_player_combo = QComboBox()
        self.injury_player_combo.setEditable(True)
        self.injury_player_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_player_combo(self.injury_player_combo)

        self.injury_label_edit = QLineEdit()
        self.injury_label_edit.setPlaceholderText(
            tr("e.g., Hamstring, shoulder surgery")
        )
        self.injury_duration_edit = QLineEdit()
        self.injury_duration_edit.setPlaceholderText(
            tr("e.g., 3 days, 3 weeks, 5-6 months")
        )
        self.injury_team_combo = QComboBox()
        self._fill_tracked_team_combo(self.injury_team_combo)
        self.injury_season_edit = QLineEdit(str(self.settings.current_season))
        self.injury_description_edit = QLineEdit()
        self.injury_notes_edit = QLineEdit()

        self.injury_label_edit.textChanged.connect(self._update_injury_description)
        self.injury_duration_edit.textChanged.connect(self._update_injury_description)

        injury_form = QFormLayout()
        injury_form.addRow(tr("Date:"), self.injury_date_edit)
        injury_form.addRow("", self.injury_date_error)
        injury_form.addRow(tr("Player:"), self.injury_player_combo)
        injury_form.addRow(tr("Injury:"), self.injury_label_edit)
        injury_form.addRow(tr("Duration:"), self.injury_duration_edit)
        injury_form.addRow(tr("Affil. Team:"), self.injury_team_combo)
        injury_form.addRow(tr("Season:"), self.injury_season_edit)
        injury_form.addRow(tr("Description:"), self.injury_description_edit)
        injury_form.addRow(tr("Notes:"), self.injury_notes_edit)

        layout.addWidget(self.injury_hint)
        layout.addLayout(injury_form)
        layout.addStretch()
        return page

    def _current_category(self) -> ManualEntryCategory:
        return "award" if self.tabs.currentIndex() == _TAB_AWARD else "milestone"

    def _on_tab_changed(self, index: int) -> None:
        if index in (_TAB_MILESTONE, _TAB_AWARD):
            self.stack.setCurrentIndex(0)
            self._reload_milestones()
            self._update_milestone_hint()
        elif index == _TAB_TRANSFER:
            self.stack.setCurrentIndex(1)
        elif index == _TAB_INJURY:
            self.stack.setCurrentIndex(2)

    def _player_registry(self) -> PlayerRegistry:
        return PlayerRegistry(self.aggregator)

    def _fill_players(self) -> None:
        self._fill_player_combo(self.player_combo)

    def _fill_player_combo(self, combo: QComboBox) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        seen_ids: set[int] = set()
        mapper = load_korean_name_mapper()
        roster_names = load_roster_player_names(
            self.settings.import_export_dir or self.settings.initial_stats_dir or None
        )
        players = self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        for player in players:
            player_id = int(player["player_id"])
            seen_ids.add(player_id)
            base_label = format_player_list_label(player)
            korean = korean_display_for_player(
                mapper,
                full_name=str(player.get("full_name") or ""),
                player_id=player_id,
                roster_names=roster_names,
            )
            label = f"{base_label} / {korean}" if korean else base_label
            combo.addItem(label, player_id)
            combo.setItemData(combo.count() - 1, base_label, Qt.ItemDataRole.UserRole + 1)
        for player in self._player_registry().list_manual_players():
            player_id = int(player["player_id"])
            if player_id in seen_ids:
                continue
            player["is_manual"] = True
            combo.addItem(format_manual_entry_label(player), player_id)
        combo.blockSignals(False)
        if current:
            combo.setEditText(current)

    def _mlb_team_names(self) -> list[str]:
        team_map = merge_team_maps(
            CANONICAL_MLB_TEAMS,
            self.settings.custom_mlb_teams,
        )
        return sorted(set(team_map.values()), key=str.lower)

    def _tracked_team_names(self) -> list[str]:
        name_map = merge_team_maps(
            CANONICAL_MLB_TEAMS,
            self.settings.custom_mlb_teams,
        )
        names: set[str] = set()
        for token in self.settings.tracked_teams:
            raw = token.strip()
            if not raw:
                continue
            upper = raw.upper()
            if upper in name_map:
                names.add(name_map[upper])
            elif raw in name_map.values():
                names.add(raw)
            else:
                names.add(raw)
        if not names:
            names.update(expand_tracked_teams(
                self.settings.tracked_teams,
                self.settings.custom_mlb_teams,
            ))
        return sorted(names, key=str.lower)

    def _fill_mlb_team_combo(self, combo: QComboBox) -> None:
        combo.clear()
        combo.addItem("", "")
        for name in self._mlb_team_names():
            combo.addItem(name, name)

    def _fill_tracked_team_combo(self, combo: QComboBox) -> None:
        combo.clear()
        for name in self._tracked_team_names():
            combo.addItem(name, name)

    def _configure_player_multipick_combo(self, combo: QComboBox) -> None:
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_player_combo(combo)
        line = combo.lineEdit()
        if line is not None:
            line.setPlaceholderText(
                tr("e.g., Dong-ju Moon, A. Judge (comma-separated)")
            )
        snapshot = {"text": ""}

        original_show_popup = combo.showPopup

        def show_popup() -> None:
            snapshot["text"] = combo.currentText()
            original_show_popup()

        combo.showPopup = show_popup  # type: ignore[method-assign]

        def on_activated(index: int) -> None:
            if index < 0:
                return
            canonical = combo.itemData(index, Qt.ItemDataRole.UserRole + 1)
            canonical_text = str(canonical) if canonical is not None else combo.itemText(index)
            picked_parts = parse_player_name_list(canonical_text)
            if not picked_parts:
                return
            picked = picked_parts[0]
            parts = parse_player_name_list(snapshot["text"])
            if picked not in parts:
                parts.append(picked)
            text = ", ".join(parts)
            if line is not None:
                line.setText(text)
            snapshot["text"] = text
            self._update_transfer_description()

        combo.activated.connect(on_activated)

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _canonical_player_text(self, combo: QComboBox) -> str:
        """Return canonical player name (without Korean suffix) from player combo."""
        text = combo.currentText().strip()
        for i in range(combo.count()):
            if combo.itemText(i).strip() == text:
                canonical = combo.itemData(i, Qt.ItemDataRole.UserRole + 1)
                if canonical is not None:
                    return str(canonical)
                break
        return text

    def _fill_teams(self) -> None:
        self.team_combo.clear()
        names = expand_tracked_teams(
            self.settings.tracked_teams,
            self.settings.custom_mlb_teams,
        )
        for name in sorted(set(names)):
            self.team_combo.addItem(name, name)

    def _reload_milestones(self) -> None:
        target = "player" if self.player_radio.isChecked() else "team"
        pool = milestones_for_manual_entry(
            self.milestones.all_milestones,
            target,
            category=self._current_category(),
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
        if self.tabs.currentIndex() == _TAB_AWARD:
            self.manual_hint.setText(
                tr(
                    "Awards, league leaders, and other items not auto-detected from boxscores."
                )
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
                tr(
                    "Can be auto-detected from boxscores, but use this to supplement or correct."
                )
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
        self._show_date_error(self.date_edit, self.date_error)

    def _validate_transfer_date_field(self) -> None:
        self._show_date_error(self.transfer_date_edit, self.transfer_date_error)

    def _validate_injury_date_field(self) -> None:
        self._show_date_error(self.injury_date_edit, self.injury_date_error)

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

    def _update_injury_description(self) -> None:
        text = build_injury_description(
            self.injury_label_edit.text(),
            self.injury_duration_edit.text(),
        )
        self.injury_description_edit.setText(text)

    def _show_date_error(self, field: QLineEdit, error_label: QLabel) -> None:
        text = field.text().strip()
        if not text:
            error_label.hide()
            return
        if parse_flexible_date(text) is None:
            error_label.setText(tr("Check date format"))
            error_label.show()
        else:
            error_label.hide()

    def _on_add_player(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            tr("Add Player"),
            tr("Enter full name (e.g., Dong-ju Moon):"),
        )
        if not ok:
            return
        try:
            player_id = self._player_registry().add_manual_player(name)
        except ValueError as exc:
            QMessageBox.warning(self, tr("Input Error"), str(exc))
            return
        for combo in (
            self.player_combo,
            self.injury_player_combo,
            self.transfer_joining_combo,
            self.transfer_leaving_combo,
        ):
            self._fill_player_combo(combo)
            index = combo.findData(player_id)
            if index >= 0 and combo is self.player_combo:
                combo.setCurrentIndex(index)

    def _resolve_player_id_from_combo(self, combo: QComboBox) -> int | None:
        text = combo.currentText().strip()
        if not text:
            return None
        for index in range(combo.count()):
            if combo.itemText(index).strip() == text:
                data = combo.itemData(index)
                if data is not None:
                    return int(data)
        return self._player_registry().resolve_player(text)

    def _ensure_player_id_from_combo(self, combo: QComboBox) -> int | None:
        player_id = self._resolve_player_id_from_combo(combo)
        if player_id is not None:
            return player_id
        text = combo.currentText().strip()
        if not text:
            return None
        try:
            return self._player_registry().ensure_player(text)
        except ValueError:
            return None

    def _build_milestone_form(self) -> ManualMilestoneFormData | None:
        parsed = parse_flexible_date(self.date_edit.text())
        if parsed is None:
            self.date_error.setText(tr("Check date format"))
            self.date_error.show()
            return None

        milestone = self._selected_milestone()
        if milestone is None:
            QMessageBox.warning(self, tr("Input Required"), tr("Please select a milestone."))
            return None

        try:
            achieved_value = float(self.value_combo.currentText().strip())
        except ValueError:
            QMessageBox.warning(self, tr("Input Error"), tr("Achieved value must be a number."))
            return None

        season: int | None = None
        if scope_needs_season(milestone.scope):
            try:
                season = int(self.season_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
                return None

        games_at: int | None = None
        if scope_needs_games_at_achievement(milestone.scope):
            try:
                games_at = int(self.games_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, tr("Input Error"), tr("Games must be an integer."))
                return None

        is_player = self.player_radio.isChecked()
        player_id: int | None = None
        if is_player:
            player_id = self._ensure_player_id_from_combo(self.player_combo)
            if player_id is None:
                QMessageBox.warning(
                    self,
                    tr("Input Required"),
                    tr("Select a player or enter a full name."),
                )
                return None
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
            opponent_team=self.opponent_team_edit.text().strip(),
            opponent_player=self.opponent_player_edit.text().strip(),
            description=self.description_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )
        errors = validate_manual_entry(form, milestone)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return None
        return form

    def _parse_optional_season(self, text: str) -> int | None:
        raw = text.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _build_transfer_form(self) -> ManualTransferFormData | None:
        parsed = parse_flexible_date(self.transfer_date_edit.text())
        if parsed is None:
            self.transfer_date_error.setText(tr("Check date format"))
            self.transfer_date_error.show()
            return None

        season = self._parse_optional_season(self.transfer_season_edit.text())
        if self.transfer_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
            return None

        form = ManualTransferFormData(
            achieved_date=parsed,
            joining_players=self._combo_text(self.transfer_joining_combo),
            leaving_players=self._combo_text(self.transfer_leaving_combo),
            event_type=str(self.transfer_type_combo.currentData()),
            join_team=self._combo_text(self.transfer_join_team_combo),
            counterpart_team=self._combo_text(self.transfer_counterpart_team_combo),
            season=season,
            description=self.transfer_description_edit.text().strip(),
            notes=self.transfer_notes_edit.text().strip(),
        )
        errors = validate_manual_transfer(form)
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return None
        return form

    def _build_injury_form(self) -> ManualInjuryFormData | None:
        parsed = parse_flexible_date(self.injury_date_edit.text())
        if parsed is None:
            self.injury_date_error.setText(tr("Check date format"))
            self.injury_date_error.show()
            return None

        season = self._parse_optional_season(self.injury_season_edit.text())
        if self.injury_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
            return None

        form = ManualInjuryFormData(
            player_name=self._canonical_player_text(self.injury_player_combo),
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
            return None
        return form

    def _checker(self) -> MilestoneChecker:
        return MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )

    def _on_accept(self) -> None:
        tab = self.tabs.currentIndex()
        checker = self._checker()

        if tab in (_TAB_MILESTONE, _TAB_AWARD):
            form = self._build_milestone_form()
            if form is None:
                return

            milestone = self.milestones.get_by_key(form.milestone_key)
            assert milestone is not None

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

            checker.record_manual_milestone(form)
            self.accept()
            return

        if tab == _TAB_TRANSFER:
            form = self._build_transfer_form()
            if form is None:
                return
            try:
                checker.record_manual_transfer(form)
            except ValueError as exc:
                QMessageBox.warning(self, tr("Input Error"), str(exc))
                return
            self.accept()
            return

        if tab == _TAB_INJURY:
            form = self._build_injury_form()
            if form is None:
                return
            try:
                checker.record_manual_injury(form)
            except ValueError as exc:
                QMessageBox.warning(self, tr("Input Error"), str(exc))
                return
            self.accept()
