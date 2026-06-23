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
from core.i18n import tr
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.team_filter import expand_tracked_teams, sorted_team_items
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import (
    add_dialog_footer,
    init_dialog_layout,
    make_button_box,
    muted_label,
)
from gui.widgets.card_panel import CardPanel


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
        self.setWindowTitle(tr("Manual Team Milestone Entry"))
        self.resize(*scale_size(420, 280))

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
        form.addRow(tr("Team"), self.team_combo)
        form.addRow(tr("Milestone"), self.milestone_combo)
        form.addRow(tr("Season"), self.season_edit)
        form.addRow(tr("Date"), self.date_edit)
        form.addRow(tr("Notes"), self.notes_edit)

        buttons = make_button_box(ok=True, ok_text="Add Record")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        form_card = CardPanel(tr("Team Milestone"))
        form_card.add_layout(form)

        layout = init_dialog_layout(self)
        layout.addWidget(
            muted_label(tr("Only manual entry items (postseason, championships, etc.) are shown."))
        )
        layout.addWidget(form_card, stretch=1)
        add_dialog_footer(layout, buttons)

    def _on_accept(self) -> None:
        team = str(self.team_combo.currentData() or "")
        milestone_key = str(self.milestone_combo.currentData() or "")
        if not team or not milestone_key:
            QMessageBox.warning(self, tr("Input Required"), tr("Please select a team and milestone."))
            return
        try:
            season = int(self.season_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, tr("Input Error"), tr("Season must be a number."))
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
                tr("Duplicate"),
                tr("This milestone has already been recorded for this season."),
            )
            return
        self.accept()
