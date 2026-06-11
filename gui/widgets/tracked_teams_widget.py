"""Tracked MLB team multi-select UI."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings
from core.stats.team_filter import CANONICAL_MLB_TEAMS, sorted_team_items


class _AddCustomTeamDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("팀 수동 추가")
        self.abbr_input = QLineEdit()
        self.abbr_input.setPlaceholderText("예: ATH")
        self.abbr_input.setMaxLength(6)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: Athletics")
        form = QFormLayout()
        form.addRow("약칭:", self.abbr_input)
        form.addRow("팀 이름:", self.name_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str] | None:
        abbr = self.abbr_input.text().strip().upper()
        name = self.name_input.text().strip()
        if not abbr or not name:
            return None
        return abbr, name


class TrackedTeamsWidget(QWidget):
    """Dropdown + list UI for selecting tracked MLB teams."""

    teams_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._custom_teams: dict[str, str] = {}
        self._selected: list[str] = []

        self.track_all_checkbox = QCheckBox("전체 선수 (팀 필터 없음)")
        self.track_all_checkbox.toggled.connect(self._on_track_all_toggled)

        self.team_combo = QComboBox()
        self.add_button = QPushButton("추가")
        self.add_button.clicked.connect(self._add_from_combo)
        self.custom_button = QPushButton("팀 수동 추가…")
        self.custom_button.clicked.connect(self._add_custom_team)

        combo_row = QHBoxLayout()
        combo_row.addWidget(self.team_combo, stretch=1)
        combo_row.addWidget(self.add_button)
        combo_row.addWidget(self.custom_button)

        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(120)
        self.remove_button = QPushButton("선택 제거")
        self.remove_button.clicked.connect(self._remove_selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.track_all_checkbox)
        layout.addLayout(combo_row)
        layout.addWidget(QLabel("추적 중인 팀:"))
        layout.addWidget(self.selected_list)
        layout.addWidget(self.remove_button)

        self._refresh_combo()

    def load_from_settings(self, settings: AppSettings) -> None:
        self._custom_teams = dict(settings.custom_mlb_teams)
        self._selected = [abbr.upper() for abbr in settings.tracked_teams]
        self.track_all_checkbox.setChecked(not settings.tracked_teams)
        self._refresh_combo()
        self._refresh_selected_list()
        self._update_enabled_state()

    def apply_to_settings(self, settings: AppSettings) -> None:
        settings.custom_mlb_teams = dict(self._custom_teams)
        if self.track_all_checkbox.isChecked():
            settings.tracked_teams = []
        else:
            settings.tracked_teams = list(self._selected)

    def get_custom_teams(self) -> dict[str, str]:
        return dict(self._custom_teams)

    def add_custom_team(self, abbr: str, name: str) -> bool:
        key = abbr.strip().upper()
        if not key or not name.strip():
            return False
        self._custom_teams[key] = name.strip()
        self._refresh_combo()
        self.teams_changed.emit()
        return True

    def team_name_map(self) -> dict[str, str]:
        merged = dict(CANONICAL_MLB_TEAMS)
        merged.update(self._custom_teams)
        return merged

    def _all_selectable_teams(self) -> dict[str, str]:
        return self.team_name_map()

    def _refresh_combo(self) -> None:
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

    def _add_custom_team(self) -> None:
        dialog = _AddCustomTeamDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values:
            QMessageBox.warning(self, "입력 필요", "약칭과 팀 이름을 모두 입력하세요.")
            return
        abbr, name = values
        if abbr in CANONICAL_MLB_TEAMS:
            QMessageBox.information(
                self,
                "이미 등록됨",
                f"{abbr}는 기본 MLB 30개 팀에 포함되어 있습니다.",
            )
            return
        if abbr in self._custom_teams:
            QMessageBox.warning(self, "중복", f"{abbr}는 이미 추가된 팀입니다.")
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
