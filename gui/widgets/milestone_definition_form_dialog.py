"""Add or edit a single milestone definition."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.milestone.definitions import (
    DESCRIPTION_TEMPLATES,
    MilestoneDefinition,
    VALID_CATEGORIES,
    VALID_DIRECTIONS,
    VALID_GRADES,
    VALID_SCOPES,
    validate_milestone_definition,
)


class MilestoneDefinitionFormDialog(QDialog):
    def __init__(
        self,
        *,
        existing_keys: set[str],
        item: MilestoneDefinition | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._existing_keys = existing_keys
        self._editing_key = item.key if item else None
        self._result: MilestoneDefinition | None = None

        self.setWindowTitle("마일스톤 기준 수정" if item else "마일스톤 기준 추가")
        self.resize(460, 420)

        self.category_combo = QComboBox()
        for value in sorted(VALID_CATEGORIES):
            self.category_combo.addItem(value, value)

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("예: career_hr_500")
        if item:
            self.key_edit.setText(item.key)
            self.key_edit.setReadOnly(True)

        self.label_edit = QLineEdit()
        self.scope_combo = QComboBox()
        for value in sorted(VALID_SCOPES):
            self.scope_combo.addItem(value, value)
        self.stat_edit = QLineEdit()
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0, 1_000_000)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(1.0)

        self.direction_combo = QComboBox()
        for value in sorted(VALID_DIRECTIONS):
            self.direction_combo.addItem(value, value)

        self.grade_combo = QComboBox()
        for value in ("common", "uncommon", "rare", "epic", "legendary"):
            self.grade_combo.addItem(value, value)

        self.track_from_spin = QDoubleSpinBox()
        self.track_from_spin.setRange(0, 1_000_000)
        self.track_from_spin.setDecimals(2)
        self.track_from_spin.setSpecialValueText("(없음)")
        self.track_from_spin.setToolTip(
            "목표까지 남은 수치가 이 값 이하일 때 예측 목록에 표시합니다. "
            "비우면 threshold의 15%입니다."
        )
        self.track_from_spin.setValue(0)

        self.near_n_spin = QDoubleSpinBox()
        self.near_n_spin.setRange(0, 1_000_000)
        self.near_n_spin.setDecimals(2)
        self.near_n_spin.setSpecialValueText("(없음)")
        self.near_n_spin.setToolTip(
            "목표까지 남은 수치가 이 값 이하일 때 임박으로 강조합니다. "
            "비우면 threshold의 5%입니다."
        )
        self.near_n_spin.setValue(0)

        self.template_combo = QComboBox()
        self.template_combo.setEditable(True)
        for value in DESCRIPTION_TEMPLATES:
            label = "(없음)" if not value else value
            self.template_combo.addItem(label, value)

        self.active_check = QCheckBox("활성 (체커·예측에 사용)")
        self.active_check.setChecked(True)

        if item:
            self._load_item(item)

        form = QFormLayout()
        form.addRow("분류:", self.category_combo)
        form.addRow("key:", self.key_edit)
        form.addRow("표시 이름:", self.label_edit)
        form.addRow("scope:", self.scope_combo)
        form.addRow("stat:", self.stat_edit)
        form.addRow("threshold:", self.threshold_spin)
        form.addRow("direction:", self.direction_combo)
        form.addRow("grade:", self.grade_combo)
        form.addRow("추적 시작 (남은 수):", self.track_from_spin)
        form.addRow("임박 (남은 수):", self.near_n_spin)
        form.addRow("설명 템플릿:", self.template_combo)
        form.addRow("", self.active_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("확인")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.scope_combo.currentTextChanged.connect(self._sync_scope_fields)
        self._sync_scope_fields()

    def result_item(self) -> MilestoneDefinition | None:
        return self._result

    def _load_item(self, item: MilestoneDefinition) -> None:
        self._set_combo_data(self.category_combo, item.category)
        self.label_edit.setText(item.label)
        self._set_combo_data(self.scope_combo, item.scope)
        self.stat_edit.setText(item.stat)
        self.threshold_spin.setValue(float(item.threshold))
        self._set_combo_data(self.direction_combo, item.direction)
        self._set_combo_data(self.grade_combo, item.grade)
        self.track_from_spin.setValue(float(item.track_from or 0))
        self.near_n_spin.setValue(float(item.near_n or 0))
        template = item.description_template or ""
        index = self.template_combo.findData(template)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)
        else:
            self.template_combo.setEditText(template)
        self.active_check.setChecked(item.active)

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _sync_scope_fields(self) -> None:
        scope = self.scope_combo.currentData()
        is_manual = scope == "team_manual"
        self.stat_edit.setEnabled(not is_manual)
        if is_manual:
            self.stat_edit.clear()
        is_ratio = scope == "season_ratio"
        self.active_check.setEnabled(not is_ratio)
        if is_ratio:
            self.active_check.setChecked(False)

    def _on_accept(self) -> None:
        scope = str(self.scope_combo.currentData())
        track_from = self.track_from_spin.value()
        near_n = self.near_n_spin.value()
        template = self.template_combo.currentData()
        if template is None:
            template = self.template_combo.currentText().strip()
        else:
            template = str(template).strip()

        active = self.active_check.isChecked()
        if scope == "season_ratio":
            active = False

        item = MilestoneDefinition(
            key=self.key_edit.text().strip(),
            label=self.label_edit.text().strip(),
            stat=self.stat_edit.text().strip(),
            threshold=float(self.threshold_spin.value()),
            scope=scope,  # type: ignore[arg-type]
            category=str(self.category_combo.currentData()),  # type: ignore[arg-type]
            direction=str(self.direction_combo.currentData()),  # type: ignore[arg-type]
            grade=str(self.grade_combo.currentData()),  # type: ignore[arg-type]
            track_from=None if track_from <= 0 else track_from,
            near_n=None if near_n <= 0 else near_n,
            description_template=template,
            active=active,
        )
        errors = validate_milestone_definition(
            item,
            existing_keys=self._existing_keys,
            editing_key=self._editing_key,
        )
        if errors:
            QMessageBox.warning(self, "입력 오류", "\n".join(errors))
            return
        self._result = item
        self.accept()
