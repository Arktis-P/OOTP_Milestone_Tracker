"""Roster bulk-edit tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, resolve_data_path
from core.roster.editor import RosterEditor, RosterFilter
from gui.widgets.table_widgets import TablePanel


class RosterView(QWidget):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.editor = RosterEditor()
        self._filtered_rows: list[dict[str, str]] = []
        self._loaded_path: Path | None = None

        self.path_label = QLabel("파일: (없음)")
        self.load_button = QPushButton("파일 선택")
        self.reload_button = QPushButton("불러오기")
        self.load_button.clicked.connect(self._pick_file)
        self.reload_button.clicked.connect(self._reload_file)

        self.position_input = QLineEdit()
        self.position_input.setPlaceholderText("전체")
        self.min_age_input = QSpinBox()
        self.max_age_input = QSpinBox()
        for spin in (self.min_age_input, self.max_age_input):
            spin.setRange(0, 60)
            spin.setSpecialValueText("—")

        self.field_combo = QComboBox()
        self.field_combo.setEditable(True)
        self.field_combo.addItems(["OVR", "CON", "POW", "SPD", "STU", "MOV", "CTL"])

        self.value_input = QLineEdit()
        self.mode_set = QRadioButton("지정값")
        self.mode_add = QRadioButton("+/-")
        self.mode_set.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_set)
        mode_group.addButton(self.mode_add)

        self.apply_filtered_button = QPushButton("필터된 전체에 적용")
        self.backup_button = QPushButton("원본 복사본 저장")
        self.save_button = QPushButton("저장")
        self.save_button.setEnabled(False)
        self.apply_filtered_button.clicked.connect(self.apply_edit)
        self.backup_button.clicked.connect(self.save_backup)
        self.save_button.clicked.connect(self.save_file)

        filter_button = QPushButton("필터 적용")
        filter_button.clicked.connect(self.apply_filter)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_label, stretch=1)
        path_row.addWidget(self.load_button)
        path_row.addWidget(self.reload_button)

        filter_form = QFormLayout()
        filter_form.addRow("포지션", self.position_input)
        filter_form.addRow("최소 나이", self.min_age_input)
        filter_form.addRow("최대 나이", self.max_age_input)
        filter_form.addRow("항목", self.field_combo)
        filter_form.addRow("변경값", self.value_input)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_set)
        mode_row.addWidget(self.mode_add)
        mode_row.addStretch()

        action_row = QHBoxLayout()
        action_row.addWidget(filter_button)
        action_row.addWidget(self.apply_filtered_button)
        action_row.addStretch()
        action_row.addWidget(self.backup_button)
        action_row.addWidget(self.save_button)

        self.table_panel = TablePanel(
            ["Name", "Team", "Position", "Age"],
            placeholder="선수 검색...",
        )
        self.info_label = QLabel("로스터 파일을 불러오세요.")

        layout = QVBoxLayout(self)
        layout.addLayout(path_row)
        layout.addLayout(filter_form)
        layout.addLayout(mode_row)
        layout.addLayout(action_row)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table_panel)

        if self.settings.roster_file:
            self._loaded_path = Path(self.settings.roster_file)
            self.path_label.setText(f"파일: {self._loaded_path}")

    def _pick_file(self) -> None:
        default_path = self.settings.roster_file or str(resolve_data_path("data"))
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "로스터 CSV 선택",
            default_path,
            "CSV Files (*.csv *.txt);;All Files (*)",
        )
        if not file_path:
            return
        self._loaded_path = Path(file_path)
        self.path_label.setText(f"파일: {self._loaded_path}")
        self._reload_file()

    def _reload_file(self) -> None:
        if not self._loaded_path or not self._loaded_path.is_file():
            QMessageBox.warning(self, "파일 없음", "먼저 로스터 파일을 선택하세요.")
            return
        try:
            self.editor.load(self._loaded_path)
        except Exception as exc:
            QMessageBox.critical(self, "로드 실패", str(exc))
            return
        self.save_button.setEnabled(False)
        self.info_label.setText(
            f"로드됨: {self._loaded_path.name} ({self.editor.row_count:,}명)"
        )
        self._filtered_rows = self.editor.snapshot_rows()
        self._show_rows(self._filtered_rows)

    def apply_filter(self) -> None:
        if not self.editor.row_count:
            QMessageBox.warning(self, "데이터 없음", "먼저 로스터를 불러오세요.")
            return
        roster_filter = RosterFilter(
            position=self.position_input.text().strip() or None,
            min_age=self.min_age_input.value() or None,
            max_age=self.max_age_input.value() or None,
        )
        self._filtered_rows = self.editor.filter_rows(roster_filter)
        self.info_label.setText(f"필터 결과: {len(self._filtered_rows):,}명")
        self._show_rows(self._filtered_rows)

    def apply_edit(self) -> None:
        field = self.field_combo.currentText().strip()
        raw_value = self.value_input.text().strip()
        if not field or not raw_value:
            QMessageBox.warning(self, "입력 필요", "항목과 변경값을 입력하세요.")
            return
        if not self._filtered_rows:
            QMessageBox.warning(self, "대상 없음", "먼저 필터를 적용하세요.")
            return
        try:
            value = float(raw_value)
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "변경값은 숫자여야 합니다.")
            return

        mode = "add" if self.mode_add.isChecked() else "set"
        modified = self.editor.bulk_edit(self._filtered_rows, field, value, mode=mode)
        QMessageBox.information(self, "수정 완료", f"{modified:,}명의 항목을 수정했습니다.")
        self.apply_filter()

    def save_backup(self) -> None:
        if not self._loaded_path:
            QMessageBox.warning(self, "파일 없음", "저장할 원본 파일이 없습니다.")
            return
        try:
            backup = self.editor.save_copy(self._loaded_path)
        except Exception as exc:
            QMessageBox.critical(self, "백업 실패", str(exc))
            return
        self.save_button.setEnabled(True)
        QMessageBox.information(self, "백업 완료", f"복사본 저장:\n{backup}")

    def save_file(self) -> None:
        if not self.editor.backup_saved:
            reply = QMessageBox.question(
                self,
                "백업 확인",
                "원본 복사본을 먼저 저장하지 않았습니다.\n지금 백업을 만든 뒤 저장할까요?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.save_backup()
        target = self._loaded_path
        if target is None:
            return
        try:
            saved = self.editor.save(target)
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        QMessageBox.information(self, "저장 완료", f"저장 위치: {saved}")

    def _show_rows(self, rows: list[dict[str, str]]) -> None:
        display_rows = []
        for row in rows[:5000]:
            display_rows.append(
                [
                    row.get("Name") or row.get("name") or "",
                    row.get("Team") or row.get("team") or "",
                    row.get("Position") or row.get("Pos") or row.get("position") or "",
                    row.get("Age") or row.get("age") or "",
                ]
            )
        self.table_panel.table.populate(display_rows)
        if len(rows) > 5000:
            self.info_label.setText(
                f"{self.info_label.text()} (표시 상한 5,000명)"
            )
