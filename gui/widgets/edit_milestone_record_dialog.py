"""Edit an existing milestone record."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.milestone.definitions import MilestoneDefinitions
from core.milestone.record_edit import (
    normalize_achieved_date,
    record_update_from_form,
    validate_record_update,
)
from core.stats.aggregator import Aggregator
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import (
    add_dialog_footer,
    init_dialog_layout,
    make_button_box,
    muted_label,
)
from gui.widgets.card_panel import CardPanel


class EditMilestoneRecordDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        record_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.record_id = record_id
        self._record = aggregator.get_milestone_record_by_id(record_id)
        if self._record is None:
            raise ValueError(f"milestone record not found: {record_id}")

        self.setWindowTitle("마일스톤 기록 수정")
        self.resize(*scale_size(480, 420))

        milestone = milestones.get_by_key(str(self._record["milestone_key"]))
        label = (
            milestone.label
            if milestone
            else self._record.get("milestone_label", self._record["milestone_key"])
        )
        is_team = bool(self._record.get("team"))
        target = str(self._record["team"]) if is_team else str(self._record["player_name"])
        scope = self._record.get("scope") or (milestone.scope if milestone else "")
        self.summary_label = muted_label(f"{target} · {label} · scope={scope}")
        self.summary_label.setObjectName("accentLabel")

        self.date_edit = QLineEdit(str(self._record.get("achieved_date") or ""))
        self.value_edit = QLineEdit(str(self._record.get("achieved_value") or ""))
        season = self._record.get("season")
        self.season_edit = QLineEdit("" if season is None else str(season))
        games = self._record.get("games_at_achievement")
        self.games_edit = QLineEdit("" if games is None else str(games))
        self.opponent_team_edit = QLineEdit(self._record.get("opponent_team") or "")
        self.opponent_player_edit = QLineEdit(self._record.get("opponent_player") or "")
        self.description_edit = QLineEdit(self._record.get("description") or "")
        self.notes_edit = QLineEdit(self._record.get("notes") or "")

        form = QFormLayout()
        form.addRow("날짜:", self.date_edit)
        form.addRow("달성값:", self.value_edit)
        form.addRow("시즌:", self.season_edit)
        form.addRow("경기수:", self.games_edit)
        form.addRow("상대팀:", self.opponent_team_edit)
        form.addRow("상대선수:", self.opponent_player_edit)
        form.addRow("설명:", self.description_edit)
        form.addRow("비고:", self.notes_edit)

        buttons = make_button_box(save=True, save_text="저장")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        form_card = CardPanel("기록 정보")
        form_card.add_layout(form)

        layout = init_dialog_layout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(form_card, stretch=1)
        add_dialog_footer(layout, buttons)

    def _on_accept(self) -> None:
        try:
            achieved_value = float(self.value_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "달성값은 숫자여야 합니다.")
            return

        try:
            update = record_update_from_form(
                achieved_date=self.date_edit.text(),
                achieved_value=achieved_value,
                season_text=self.season_edit.text(),
                games_text=self.games_edit.text(),
                opponent_team=self.opponent_team_edit.text(),
                opponent_player=self.opponent_player_edit.text(),
                description=self.description_edit.text(),
                notes=self.notes_edit.text(),
            )
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "시즌·경기수는 정수여야 합니다.")
            return

        scope = str(self._record.get("scope") or "")
        errors = validate_record_update(update, scope=scope)
        if errors:
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
            return

        try:
            achieved_date = normalize_achieved_date(update.achieved_date)
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return

        if not self.aggregator.update_milestone_record(
            self.record_id,
            achieved_date=achieved_date,
            achieved_value=update.achieved_value,
            season=update.season,
            games_at_achievement=update.games_at_achievement,
            opponent_team=update.opponent_team,
            opponent_player=update.opponent_player,
            description=update.description,
            notes=update.notes,
        ):
            QMessageBox.warning(self, "저장 실패", "기록을 찾을 수 없습니다.")
            return
        self.accept()
