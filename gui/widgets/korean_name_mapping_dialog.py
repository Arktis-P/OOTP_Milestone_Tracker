"""Dialog to translate pending roman name parts into Korean mappings."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.roster.korean_names import KoreanNameStore, PendingName, pending_full_name_label
from gui.ui_compact import scale_size


class KoreanNameMappingDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("한글 이름 매핑")
        self.resize(*scale_size(720, 520))
        self._store = KoreanNameStore.load()

        intro = QLabel(
            "박스스코어·스탯 불러오기 중 등록되지 않은 성/이름이 여기에 쌓입니다.\n"
            "OOTP 풀 네임(First Last) 기준으로 성·이름을 나눠 매핑합니다. "
            "한국인은 성+이름, 그 외는 이름+성 순으로 표시됩니다."
        )
        intro.setWordWrap(True)

        self.summary_label = QLabel()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("로마자 검색...")
        self.search_input.textChanged.connect(self._reload_table)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["구분", "풀 네임(참고)", "로마자", "한글 표기", "출처"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 140)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        save_button = QPushButton("입력한 항목 저장")
        save_button.clicked.connect(self._save_entries)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(self.summary_label, stretch=1)
        top_row.addWidget(self.search_input, stretch=1)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(top_row)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(buttons)

        self._reload_table()

    def _reload_table(self) -> None:
        needle = self.search_input.text().strip().casefold()
        rows = self._store.pending
        if needle:
            rows = [row for row in rows if needle in row.name.casefold()]

        self.summary_label.setText(
            f"한글 표기 필요: {self._store.pending_count():,}건"
            + (f" · 표시 {len(rows):,}건" if needle else "")
        )

        self.table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            self.table.setItem(row_idx, 0, self._read_only_item(self._part_label(item.part)))
            self.table.setItem(
                row_idx, 1, self._read_only_item(pending_full_name_label(item))
            )
            name_item = self._read_only_item(item.name)
            name_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row_idx, 2, name_item)
            self.table.setItem(row_idx, 3, QTableWidgetItem(""))
            self.table.setItem(row_idx, 4, self._read_only_item(item.source or "-"))

    @staticmethod
    def _part_label(part: str) -> str:
        return "성" if part == "last" else "이름"

    @staticmethod
    def _read_only_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _save_entries(self) -> None:
        saved = 0
        errors: list[str] = []
        for row_idx in range(self.table.rowCount()):
            base_item = self.table.item(row_idx, 2)
            korean_item = self.table.item(row_idx, 3)
            if base_item is None or korean_item is None:
                continue
            pending = base_item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(pending, PendingName):
                continue
            korean = korean_item.text().strip()
            if not korean:
                continue
            try:
                self._store.apply_mapping(pending.part, pending.name, korean)
                saved += 1
            except ValueError as exc:
                errors.append(str(exc))
            except OSError as exc:
                errors.append(str(exc) or "한글 매핑 파일을 저장하지 못했습니다.")
                break

        if errors:
            QMessageBox.warning(self, "저장 오류", "\n".join(errors[:5]))
        if saved:
            QMessageBox.information(self, "저장 완료", f"{saved:,}건의 한글 표기를 저장했습니다.")
            self._reload_table()
        elif not errors:
            QMessageBox.information(self, "변경 없음", "저장할 한글 표기가 없습니다.")
