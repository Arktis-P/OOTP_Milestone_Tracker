"""Roster bulk-edit tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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

        self.load_button = QPushButton("로스터 파일 열기")
        self.apply_button = QPushButton("일괄 수정 적용")
        self.save_button = QPushButton("저장")
        self.load_button.clicked.connect(self.load_file)
        self.apply_button.clicked.connect(self.apply_edit)
        self.save_button.clicked.connect(self.save_file)

        self.position_input = QLineEdit()
        self.min_age_input = QSpinBox()
        self.max_age_input = QSpinBox()
        self.rating_field_input = QLineEdit()
        self.min_rating_input = QLineEdit()
        self.max_rating_input = QLineEdit()
        self.new_rating_input = QLineEdit()

        for spin in (self.min_age_input, self.max_age_input):
            spin.setRange(0, 60)
            spin.setSpecialValueText("—")

        filter_form = QFormLayout()
        filter_form.addRow("포지션", self.position_input)
        filter_form.addRow("최소 나이", self.min_age_input)
        filter_form.addRow("최대 나이", self.max_age_input)
        filter_form.addRow("레이팅 필드", self.rating_field_input)
        filter_form.addRow("최소 레이팅", self.min_rating_input)
        filter_form.addRow("최대 레이팅", self.max_rating_input)
        filter_form.addRow("새 레이팅 값", self.new_rating_input)

        filter_button = QPushButton("필터 적용")
        filter_button.clicked.connect(self.apply_filter)

        button_row = QHBoxLayout()
        button_row.addWidget(self.load_button)
        button_row.addWidget(filter_button)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.save_button)
        button_row.addStretch()

        self.table_panel = TablePanel(
            ["Name", "Team", "Position"],
            placeholder="선수 검색...",
        )
        self.info_label = QLabel("로스터 파일을 불러오세요.")

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addLayout(filter_form)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table_panel)

    def load_file(self) -> None:
        default_path = self.settings.roster_file or str(resolve_data_path("data"))
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "로스터 CSV 선택",
            default_path,
            "CSV Files (*.csv *.txt);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self.editor.load(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "로드 실패", str(exc))
            return

        self.info_label.setText(f"로드됨: {Path(file_path).name} ({self.editor.row_count}명)")
        self._show_rows(self.editor.snapshot_rows())

    def apply_filter(self) -> None:
        roster_filter = RosterFilter(
            position=self.position_input.text().strip() or None,
            min_age=self.min_age_input.value() or None,
            max_age=self.max_age_input.value() or None,
            rating_field=self.rating_field_input.text().strip() or None,
            min_rating=self._parse_float(self.min_rating_input.text()),
            max_rating=self._parse_float(self.max_rating_input.text()),
        )
        self._filtered_rows = self.editor.filter_rows(roster_filter)
        self.info_label.setText(f"필터 결과: {len(self._filtered_rows)}명")
        self._show_rows(self._filtered_rows)

    def apply_edit(self) -> None:
        rating_field = self.rating_field_input.text().strip()
        new_value = self.new_rating_input.text().strip()
        if not rating_field or not new_value:
            QMessageBox.warning(self, "입력 필요", "레이팅 필드와 새 값을 입력하세요.")
            return
        if not self._filtered_rows:
            QMessageBox.warning(self, "대상 없음", "먼저 필터를 적용하세요.")
            return

        modified = self.editor.bulk_edit_rating(self._filtered_rows, rating_field, new_value)
        QMessageBox.information(self, "수정 완료", f"{modified}명의 레이팅을 수정했습니다.")
        self.apply_filter()

    def save_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "로스터 저장",
            self.settings.roster_file or "",
            "CSV Files (*.csv);;Text Files (*.txt)",
        )
        if not file_path:
            return
        try:
            saved = self.editor.save(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        QMessageBox.information(self, "저장 완료", f"저장 위치: {saved}")

    def _show_rows(self, rows: list[dict[str, str]]) -> None:
        display_rows = []
        for row in rows:
            display_rows.append(
                [
                    row.get("Name") or row.get("name") or "",
                    row.get("Team") or row.get("team") or "",
                    row.get("Position") or row.get("Pos") or row.get("position") or "",
                ]
            )
        self.table_panel.table.populate(display_rows)

    @staticmethod
    def _parse_float(value: str) -> float | None:
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
