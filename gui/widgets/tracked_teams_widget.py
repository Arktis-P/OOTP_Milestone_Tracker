"""Tracked MLB team multi-select UI."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.i18n import tr
from core.stats.team_filter import CANONICAL_MLB_TEAMS, sorted_team_items
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box
from gui.widgets.card_panel import CardPanel


class _AddCustomTeamDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Add Custom Team"))
        self.abbr_input = QLineEdit()
        self.abbr_input.setPlaceholderText("e.g.: ATH")
        self.abbr_input.setMaxLength(6)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g.: Athletics")
        form = QFormLayout()
        form.addRow(tr("Abbreviation:"), self.abbr_input)
        form.addRow(tr("Team Name:"), self.name_input)
        buttons = make_button_box(ok=True, ok_text="Add")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form_card = CardPanel(tr("Team Info"))
        form_card.add_layout(form)

        layout = init_dialog_layout(self)
        layout.addWidget(form_card)
        add_dialog_footer(layout, buttons)

    def values(self) -> tuple[str, str] | None:
        abbr = self.abbr_input.text().strip().upper()
        name = self.name_input.text().strip()
        if not abbr or not name:
            return None
        return abbr, name


class TrackedTeamsWidget(QWidget):
    """Dropdown + list UI, or checkbox list for compact settings layout."""

    teams_changed = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        checkbox_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._checkbox_mode = checkbox_mode
        self._custom_teams: dict[str, str] = {}
        self._selected: list[str] = []
        self._team_checkboxes: dict[str, QCheckBox] = {}

        self.track_all_checkbox = QCheckBox(tr("All Players (no team filter)"))
        self.track_all_checkbox.toggled.connect(self._on_track_all_toggled)

        if checkbox_mode:
            self._build_checkbox_ui()
        else:
            self._build_combo_ui()

    def _build_combo_ui(self) -> None:
        self.team_combo = QComboBox()
        self.add_button = QPushButton(tr("Add"))
        self.add_button.clicked.connect(self._add_from_combo)
        self.custom_button = QPushButton(tr("Add Custom Team..."))
        self.custom_button.clicked.connect(self._add_custom_team)

        combo_row = QHBoxLayout()
        combo_row.addWidget(self.team_combo, stretch=1)
        combo_row.addWidget(self.add_button)
        combo_row.addWidget(self.custom_button)

        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(90)
        self.remove_button = QPushButton(tr("Remove Selected"))
        self.remove_button.clicked.connect(self._remove_selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.track_all_checkbox)
        layout.addLayout(combo_row)
        layout.addWidget(QLabel(tr("Tracked Teams:")))
        layout.addWidget(self.selected_list)
        layout.addWidget(self.remove_button)

        self._refresh_combo()

    def _build_checkbox_ui(self) -> None:
        self._checkbox_host = QWidget()
        self._checkbox_layout = QVBoxLayout(self._checkbox_host)
        self._checkbox_layout.setContentsMargins(4, 4, 4, 4)
        self._checkbox_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._checkbox_host)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.track_all_checkbox)
        layout.addWidget(scroll)

    def load_from_settings(self, settings: AppSettings) -> None:
        self._custom_teams = dict(settings.custom_mlb_teams)
        self._selected = [abbr.upper() for abbr in settings.tracked_teams]
        self.track_all_checkbox.blockSignals(True)
        self.track_all_checkbox.setChecked(not settings.tracked_teams)
        self.track_all_checkbox.blockSignals(False)
        if self._checkbox_mode:
            self._rebuild_checkboxes()
        else:
            self._refresh_combo()
            self._refresh_selected_list()
        self._update_enabled_state()

    def apply_to_settings(self, settings: AppSettings) -> None:
        settings.custom_mlb_teams = dict(self._custom_teams)
        if self.track_all_checkbox.isChecked():
            settings.tracked_teams = []
        elif self._checkbox_mode:
            settings.tracked_teams = [
                abbr
                for abbr, checkbox in self._team_checkboxes.items()
                if checkbox.isChecked()
            ]
        else:
            settings.tracked_teams = list(self._selected)

    def get_custom_teams(self) -> dict[str, str]:
        return dict(self._custom_teams)

    def add_custom_team(self, abbr: str, name: str) -> bool:
        key = abbr.strip().upper()
        if not key or not name.strip():
            return False
        self._custom_teams[key] = name.strip()
        if key not in self._selected:
            self._selected.append(key)
        if self._checkbox_mode:
            self._rebuild_checkboxes()
        else:
            self._refresh_combo()
        self.teams_changed.emit()
        return True

    def team_name_map(self) -> dict[str, str]:
        merged = dict(CANONICAL_MLB_TEAMS)
        merged.update(self._custom_teams)
        return merged

    def _all_selectable_teams(self) -> dict[str, str]:
        return self.team_name_map()

    def _rebuild_checkboxes(self) -> None:
        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._team_checkboxes.clear()

        for abbr, name in sorted_team_items(self._all_selectable_teams()):
            label = f"[{abbr}] {name}"
            checkbox = QCheckBox(label)
            checkbox.setChecked(abbr in self._selected)
            checkbox.toggled.connect(self._on_checkbox_toggled)
            self._team_checkboxes[abbr] = checkbox
            self._checkbox_layout.addWidget(checkbox)
        self._checkbox_layout.addStretch()

    def _on_checkbox_toggled(self, _checked: bool) -> None:
        self._selected = [
            abbr for abbr, cb in self._team_checkboxes.items() if cb.isChecked()
        ]
        self.teams_changed.emit()

    def _refresh_combo(self) -> None:
        if self._checkbox_mode:
            return
        current = self.team_combo.currentData()
        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        for abbr, name in sorted_team_items(self._all_selectable_teams()):
            self.team_combo.addItem(f"{abbr} — {name}", abbr)
        if current is not None:
            index = self.team_combo.findData(current)
            if index >= 0:
                self.team_combo.setCurrentIndex(index)
        self.team_combo.blockSignals(False)

    def _refresh_selected_list(self) -> None:
        if self._checkbox_mode:
            return
        self.selected_list.clear()
        name_map = self._all_selectable_teams()
        for abbr in self._selected:
            label = f"{abbr} — {name_map.get(abbr, abbr)}"
            item = QListWidgetItem(label)
            item.setData(256, abbr)
            self.selected_list.addItem(item)

    def _on_track_all_toggled(self, checked: bool) -> None:
        self._update_enabled_state()
        self.teams_changed.emit()

    def _update_enabled_state(self) -> None:
        enabled = not self.track_all_checkbox.isChecked()
        if self._checkbox_mode:
            for checkbox in self._team_checkboxes.values():
                checkbox.setEnabled(enabled)
            return
        for widget in (
            self.team_combo,
            self.add_button,
            self.custom_button,
            self.selected_list,
            self.remove_button,
        ):
            widget.setEnabled(enabled)

    def _add_from_combo(self) -> None:
        abbr = self.team_combo.currentData()
        if not abbr:
            return
        abbr = str(abbr).upper()
        if abbr in self._selected:
            return
        self._selected.append(abbr)
        self._refresh_selected_list()
        self.teams_changed.emit()

    def add_custom_team_dialog(self) -> None:
        self._add_custom_team()

    def _add_custom_team(self) -> None:
        dialog = _AddCustomTeamDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values:
            QMessageBox.warning(self, tr("Input Required"), tr("Please enter both an abbreviation and a team name."))
            return
        abbr, name = values
        if abbr in CANONICAL_MLB_TEAMS:
            QMessageBox.information(
                self,
                tr("Already Registered"),
                tr("{abbr} is already in the standard 30 MLB teams.").format(abbr=abbr),
            )
            return
        if abbr in self._custom_teams:
            QMessageBox.warning(self, tr("Duplicate"), tr("{abbr} has already been added.").format(abbr=abbr))
            return
        self.add_custom_team(abbr, name)

    def _remove_selected(self) -> None:
        row = self.selected_list.currentRow()
        if row < 0:
            return
        item = self.selected_list.item(row)
        abbr = str(item.data(256))
        self._selected = [team for team in self._selected if team != abbr]
        self._refresh_selected_list()
        self.teams_changed.emit()
