"""Manual team milestone entry dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.config import AppSettings
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams, sorted_team_items


class TeamMilestoneDialog(QDialog):
    def __init__(
        self,
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.setWindowTitle("팀 마일스톤 수동 입력")
        self.resize(420, 280)

        self.team_combo = QComboBox()
        team_map = {
            **settings.team_name_map(),
            **settings.custom_mlb_teams,
        }
        tokens = settings.tracked_teams or []
        if tokens:
            expanded = expand_tracked_teams(tokens, settings.custom_mlb_teams)
            for abbr in tokens:
                name = team_map.get(abbr.upper(), abbr)
                self.team_combo.addItem(f"{abbr} — {name}", name)
            for name in sorted(set(expanded) - {team_map.get(t.upper(), t) for t in tokens}):
                self.team_combo.addItem(name, name)
        else:
            for abbr, name in sorted_team_items(team_map):
                self.team_combo.addItem(f"{abbr} — {name}", name)

        self.milestone_combo = QComboBox()
        for milestone in milestones.team:
            if milestone.scope == "team_manual" and milestone.active:
                self.milestone_combo.addItem(milestone.label, milestone.key)

        self.season_edit = QLineEdit(str(settings.current_season))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.notes_edit = QLineEdit()

        form = QFormLayout()
        form.addRow("팀", self.team_combo)
        form.addRow("마일스톤", self.milestone_combo)
        form.addRow("시즌", self.season_edit)
        form.addRow("날짜", self.date_edit)
        form.addRow("메모", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("포스트시즌·우승 등 수동 기록 항목만 표시됩니다."))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        team = str(self.team_combo.currentData() or "")
        milestone_key = str(self.milestone_combo.currentData() or "")
        if not team or not milestone_key:
            QMessageBox.warning(self, "입력 필요", "팀과 마일스톤을 선택하세요.")
            return
        try:
            season = int(self.season_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "시즌은 숫자여야 합니다.")
            return

        checker = MilestoneChecker(
            self.aggregator,
            self.milestones,
            season_games_total=self.settings.season_games_total,
            ratio_qualifiers=self.settings.get_ratio_qualifiers(),
            tracked_teams=self.settings.tracked_teams,
            custom_teams=self.settings.custom_mlb_teams,
        )
        recorded = checker.record_manual_team_milestone(
            team=team,
            milestone_key=milestone_key,
            season=season,
            achieved_date=self.date_edit.date().toString("yyyy-MM-dd"),
            notes=self.notes_edit.text().strip(),
        )
        if not recorded:
            QMessageBox.warning(
                self,
                "중복",
                "이미 해당 시즌에 기록된 마일스톤입니다.",
            )
            return
        self.accept()
