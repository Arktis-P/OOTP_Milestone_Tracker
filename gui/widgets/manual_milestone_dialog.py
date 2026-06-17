"""Unified manual milestone entry dialog with category tabs."""

from __future__ import annotations

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
from core.stats.player_display import format_manual_entry_label, format_player_list_label
from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    expand_tracked_teams,
    merge_team_maps,
)

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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.setWindowTitle("수동 입력")
        self.resize(540, 560)

        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), "마일스톤")
        self.tabs.addTab(QWidget(), "수상")
        self.tabs.addTab(QWidget(), "이적")
        self.tabs.addTab(QWidget(), "부상")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_milestone_page())
        self.stack.addWidget(self._build_transfer_page())
        self.stack.addWidget(self._build_injury_page())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("기록 추가")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.stack)
        layout.addWidget(buttons)

        self._on_tab_changed(0)

    def _build_milestone_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.player_radio = QRadioButton("개인")
        self.team_radio = QRadioButton("팀")
        self.player_radio.setChecked(True)
        self.player_radio.toggled.connect(self._on_target_changed)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("대상:"))
        target_row.addWidget(self.player_radio)
        target_row.addWidget(self.team_radio)
        target_row.addStretch()

        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("2026-03-01")
        self.date_error = QLabel("")
        self.date_error.setStyleSheet("color: #dc2626;")
        self.date_error.hide()
        self.date_edit.textChanged.connect(self._validate_date_field)

        self.player_combo = QComboBox()
        self.player_combo.setEditable(True)
        self.player_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_players()
        line = self.player_combo.lineEdit()
        if line is not None:
            line.setPlaceholderText("풀 네임 입력 또는 목록 선택 (예: Dong-ju Moon)")
        self.add_player_button = QPushButton("+ 선수 추가")
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
        self.manual_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        self.manual_hint.setText(
            "추적 팀 선수는 목록에서 고르고, 아직 DB에 없는 선수는 풀 네임을 "
            "직접 입력하거나 '+ 선수 추가'로 등록할 수 있습니다."
        )

        self.season_edit = QLineEdit(str(self.settings.current_season))
        self.season_label = QLabel("시즌:")
        self.season_row_widget = QWidget()
        season_layout = QHBoxLayout(self.season_row_widget)
        season_layout.setContentsMargins(0, 0, 0, 0)
        season_layout.addWidget(self.season_edit)

        self.games_edit = QLineEdit()
        self.games_edit.setPlaceholderText("이 시점까지 출장한 경기수")
        self.games_label = QLabel("동안 경기수:")
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
        self.form.addRow("날짜:", self.date_edit)
        self.form.addRow("", self.date_error)
        self.form.addRow("선수:", self.player_row_widget)
        self.form.addRow("팀:", self.team_row_widget)
        self.form.addRow("마일스톤:", self.milestone_combo)
        self.form.addRow(self.season_label, self.season_row_widget)
        self.form.addRow(self.games_label, self.games_row_widget)
        self.form.addRow("달성값:", self.value_combo)
        self.form.addRow("상대팀:", self.opponent_team_edit)
        self.form.addRow("상대선수:", self.opponent_player_edit)
        self.form.addRow("설명:", self.description_edit)
        self.form.addRow("비고:", self.notes_edit)

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
            "계약·트레이드 등 선수 이동 내역을 기록합니다. "
            "합류·이탈 선수는 쉼표로 구분하세요."
        )
        self.transfer_hint.setWordWrap(True)
        self.transfer_hint.setStyleSheet("color: #64748b; font-size: 12px;")

        self.transfer_date_edit = QLineEdit()
        self.transfer_date_edit.setPlaceholderText("2026-03-01")
        self.transfer_date_error = QLabel("")
        self.transfer_date_error.setStyleSheet("color: #dc2626;")
        self.transfer_date_error.hide()
        self.transfer_date_edit.textChanged.connect(self._validate_transfer_date_field)

        self.transfer_joining_combo = QComboBox()
        self.transfer_leaving_combo = QComboBox()
        self._configure_player_multipick_combo(self.transfer_joining_combo)
        self._configure_player_multipick_combo(self.transfer_leaving_combo)

        self.transfer_type_combo = QComboBox()
        for key, label in TRANSFER_EVENT_LABELS.items():
            self.transfer_type_combo.addItem(label, key)
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
        transfer_form.addRow("날짜:", self.transfer_date_edit)
        transfer_form.addRow("", self.transfer_date_error)
        transfer_form.addRow("합류:", self.transfer_joining_combo)
        transfer_form.addRow("이탈:", self.transfer_leaving_combo)
        transfer_form.addRow("유형:", self.transfer_type_combo)
        transfer_form.addRow("합류팀:", self.transfer_join_team_combo)
        transfer_form.addRow("상대팀:", self.transfer_counterpart_team_combo)
        transfer_form.addRow("시즌:", self.transfer_season_edit)
        transfer_form.addRow("설명:", self.transfer_description_edit)
        transfer_form.addRow("비고:", self.transfer_notes_edit)

        layout.addWidget(self.transfer_hint)
        layout.addLayout(transfer_form)
        layout.addStretch()
        return page

    def _build_injury_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.injury_hint = QLabel("선수 부상 발생·복귀 등 부상 관련 내역을 기록합니다.")
        self.injury_hint.setWordWrap(True)
        self.injury_hint.setStyleSheet("color: #64748b; font-size: 12px;")

        self.injury_date_edit = QLineEdit()
        self.injury_date_edit.setPlaceholderText("2026-03-01")
        self.injury_date_error = QLabel("")
        self.injury_date_error.setStyleSheet("color: #dc2626;")
        self.injury_date_error.hide()
        self.injury_date_edit.textChanged.connect(self._validate_injury_date_field)

        self.injury_player_combo = QComboBox()
        self.injury_player_combo.setEditable(True)
        self.injury_player_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_player_combo(self.injury_player_combo)

        self.injury_label_edit = QLineEdit()
        self.injury_label_edit.setPlaceholderText("예: 햄스트링, 어깨 수술")
        self.injury_duration_edit = QLineEdit()
        self.injury_duration_edit.setPlaceholderText("예: 3일, 3주, 5-6달")
        self.injury_team_combo = QComboBox()
        self._fill_tracked_team_combo(self.injury_team_combo)
        self.injury_season_edit = QLineEdit(str(self.settings.current_season))
        self.injury_description_edit = QLineEdit()
        self.injury_notes_edit = QLineEdit()

        self.injury_label_edit.textChanged.connect(self._update_injury_description)
        self.injury_duration_edit.textChanged.connect(self._update_injury_description)

        injury_form = QFormLayout()
        injury_form.addRow("날짜:", self.injury_date_edit)
        injury_form.addRow("", self.injury_date_error)
        injury_form.addRow("선수:", self.injury_player_combo)
        injury_form.addRow("부상:", self.injury_label_edit)
        injury_form.addRow("기간:", self.injury_duration_edit)
        injury_form.addRow("소속팀:", self.injury_team_combo)
        injury_form.addRow("시즌:", self.injury_season_edit)
        injury_form.addRow("설명:", self.injury_description_edit)
        injury_form.addRow("비고:", self.injury_notes_edit)

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
        players = self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        for player in players:
            player_id = int(player["player_id"])
            seen_ids.add(player_id)
            combo.addItem(
                format_player_list_label(player),
                player_id,
            )
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
        combo.addItem("", "")
        for name in self._tracked_team_names():
            combo.addItem(name, name)

    def _configure_player_multipick_combo(self, combo: QComboBox) -> None:
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fill_player_combo(combo)
        line = combo.lineEdit()
        if line is not None:
            line.setPlaceholderText("예: Dong-ju Moon, A. Judge (쉼표 구분)")
        snapshot = {"text": ""}

        original_show_popup = combo.showPopup

        def show_popup() -> None:
            snapshot["text"] = combo.currentText()
            original_show_popup()

        combo.showPopup = show_popup  # type: ignore[method-assign]

        def on_activated(index: int) -> None:
            if index < 0:
                return
            picked_parts = parse_player_name_list(combo.itemText(index))
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
                "수상·리그 1위 등 박스스코어에서 자동 판정되지 않는 항목입니다."
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
                "박스스코어로 자동 판정 가능하지만 수동으로 보완·수정할 때 사용합니다."
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
            error_label.setText("날짜 형식을 확인하세요")
            error_label.show()
        else:
            error_label.hide()

    def _on_add_player(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "선수 추가",
            "풀 네임을 입력하세요 (예: Dong-ju Moon):",
        )
        if not ok:
            return
        try:
            player_id = self._player_registry().add_manual_player(name)
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
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
            self.date_error.setText("날짜 형식을 확인하세요")
            self.date_error.show()
            return None

        milestone = self._selected_milestone()
        if milestone is None:
            QMessageBox.warning(self, "입력 필요", "마일스톤을 선택하세요.")
            return None

        try:
            achieved_value = float(self.value_combo.currentText().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "달성값은 숫자여야 합니다.")
            return None

        season: int | None = None
        if scope_needs_season(milestone.scope):
            try:
                season = int(self.season_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, "입력 오류", "시즌은 숫자여야 합니다.")
                return None

        games_at: int | None = None
        if scope_needs_games_at_achievement(milestone.scope):
            try:
                games_at = int(self.games_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, "입력 오류", "동안 경기수는 정수여야 합니다.")
                return None

        is_player = self.player_radio.isChecked()
        player_id: int | None = None
        if is_player:
            player_id = self._ensure_player_id_from_combo(self.player_combo)
            if player_id is None:
                QMessageBox.warning(
                    self,
                    "입력 필요",
                    "선수를 선택하거나 풀 네임을 입력하세요.",
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
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
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
            self.transfer_date_error.setText("날짜 형식을 확인하세요")
            self.transfer_date_error.show()
            return None

        season = self._parse_optional_season(self.transfer_season_edit.text())
        if self.transfer_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, "입력 오류", "시즌은 숫자여야 합니다.")
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
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
            return None
        return form

    def _build_injury_form(self) -> ManualInjuryFormData | None:
        parsed = parse_flexible_date(self.injury_date_edit.text())
        if parsed is None:
            self.injury_date_error.setText("날짜 형식을 확인하세요")
            self.injury_date_error.show()
            return None

        season = self._parse_optional_season(self.injury_season_edit.text())
        if self.injury_season_edit.text().strip() and season is None:
            QMessageBox.warning(self, "입력 오류", "시즌은 숫자여야 합니다.")
            return None

        form = ManualInjuryFormData(
            player_name=self._combo_text(self.injury_player_combo),
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
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
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
                    "중복 확인",
                    f"{dup_msg}\n그래도 추가하시겠습니까?",
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
                QMessageBox.warning(self, "입력 오류", str(exc))
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
                QMessageBox.warning(self, "입력 오류", str(exc))
                return
            self.accept()
