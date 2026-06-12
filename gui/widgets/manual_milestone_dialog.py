"""Unified manual milestone entry dialog (player + team)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.manual_entry import (
    ManualMilestoneFormData,
    check_duplicate,
    get_achieved_value_candidates,
    milestones_for_target,
    parse_flexible_date,
    scope_needs_games_at_achievement,
    scope_needs_season,
    validate_manual_entry,
)
from core.roster.player_registry import PlayerRegistry
from core.stats.aggregator import Aggregator
from core.stats.player_display import format_player_list_label
from core.stats.team_filter import expand_tracked_teams


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
        self.setWindowTitle("마일스톤 수동 입력")
        self.resize(520, 480)

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

        self.season_edit = QLineEdit(str(settings.current_season))
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
        self.form.addRow("마일스톤 설명:", self.description_edit)
        self.form.addRow("비고:", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("기록 추가")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(target_row)
        layout.addLayout(self.form)
        layout.addWidget(buttons)

        self._reload_milestones()
        self._on_target_changed()

    def _fill_players(self) -> None:
        self.player_combo.clear()
        players = self.aggregator.get_tracked_players(
            self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        for player in players:
            self.player_combo.addItem(
                format_player_list_label(player),
                int(player["player_id"]),
            )

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
        pool = milestones_for_target(self.milestones.all_milestones, target)
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

    def _on_milestone_changed(self) -> None:
        milestone = self._selected_milestone()
        if milestone is None:
            return
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
            self.date_error.setText("날짜 형식을 확인하세요")
            self.date_error.show()
        else:
            self.date_error.hide()

    def _on_add_player(self) -> None:
        try:
            PlayerRegistry(self.aggregator).add_player_stub("")
        except NotImplementedError:
            QMessageBox.information(
                self,
                "선수 추가",
                "이 기능은 추후 지원됩니다.",
            )

    def _build_form(self) -> ManualMilestoneFormData | None:
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
        player_id = self.player_combo.currentData() if is_player else None
        team = self.team_combo.currentData() if not is_player else None

        form = ManualMilestoneFormData(
            target="player" if is_player else "team",
            achieved_date=parsed,
            player_id=int(player_id) if player_id is not None else None,
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

    def _on_accept(self) -> None:
        form = self._build_form()
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

        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        checker.record_manual_milestone(form)
        self.accept()
