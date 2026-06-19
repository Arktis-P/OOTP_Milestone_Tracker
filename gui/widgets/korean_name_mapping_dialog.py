"""Dialog to translate pending roman name parts into Korean mappings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
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
from core.roster.korean_name_suggest import suggest_korean_name
from gui.theme import TEXT_MUTED, TEXT_PRIMARY
from gui.ui_compact import scale_size
from gui.utils.file_open import open_path_in_default_app
from gui.widgets.app_dialog import (
    init_dialog_layout,
    make_button_box,
    muted_label,
    style_primary_button,
    summary_label,
    table_card,
)

SUGGESTION_ROLE = Qt.ItemDataRole.UserRole + 1


class KoreanNameMappingDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("한글 이름 매핑")
        self.resize(*scale_size(1440, 1300))
        self._store = KoreanNameStore.load()
        self._updating_table = False

        intro = muted_label(
            "박스스코어·스탯 불러오기 중 등록되지 않은 성/이름이 여기에 쌓입니다.\n"
            "OOTP 풀 네임(First Last) 기준으로 성·이름을 나눠 매핑합니다. "
            "한국인은 성+이름, 그 외는 이름+성 순으로 표시됩니다.\n"
            "회색 추천 표기는 번들·사용자 매핑 CSV와 MLB 중계식 규칙을 바탕으로 자동 제안합니다. "
            "그대로 두고 저장하면 매핑에 반영되며, 지우면 저장에서 제외됩니다."
        )

        self.summary_label = summary_label()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("로마자 검색...")
        self.search_input.textChanged.connect(self._reload_table)

        self.refresh_button = QPushButton("목록 새로고침")
        self.refresh_button.clicked.connect(self._reload_table)

        csv_row = QHBoxLayout()
        csv_row.setSpacing(8)
        csv_row.addWidget(muted_label("CSV 편집:", wrap=False))
        self._csv_buttons: list[tuple[str, Path]] = []
        for label, filename in (
            ("성 매핑 CSV", "korean_last_names.csv"),
            ("이름 매핑 CSV", "korean_first_names.csv"),
            ("대기 목록 CSV", "korean_names_pending.csv"),
        ):
            button = QPushButton(label)
            path = self._store.data_dir / filename
            button.clicked.connect(lambda _checked=False, p=path: self._open_csv(p))
            csv_row.addWidget(button)
            self._csv_buttons.append((label, path))
        csv_row.addStretch()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["구분", "풀 네임(참고)", "로마자", "한글 표기 (추천)", "출처"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 180)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)

        save_button = QPushButton("입력한 항목 저장")
        save_button.clicked.connect(self._save_entries)
        style_primary_button(save_button)

        buttons = make_button_box(close=True, cancel=False)
        buttons.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self.summary_label, stretch=1)
        top_row.addWidget(self.search_input, stretch=1)
        top_row.addWidget(self.refresh_button)

        table_panel = table_card("매핑 대기 목록", self.table)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(save_button)
        footer.addWidget(buttons)

        layout = init_dialog_layout(self)
        layout.addWidget(intro)
        layout.addLayout(csv_row)
        layout.addLayout(top_row)
        layout.addWidget(table_panel, stretch=1)
        layout.addLayout(footer)

        self._reload_table()

    def _open_csv(self, path: Path) -> None:
        if not path.is_file():
            QMessageBox.warning(
                self,
                "파일 없음",
                f"CSV 파일을 찾을 수 없습니다.\n{path}",
            )
            return
        if not open_path_in_default_app(path):
            QMessageBox.warning(
                self,
                "열기 실패",
                "기본 프로그램으로 CSV를 열지 못했습니다.\n"
                f"경로: {path}",
            )

    def _reload_table(self) -> None:
        self._store = KoreanNameStore.load()
        needle = self.search_input.text().strip().casefold()
        rows = self._store.pending
        if needle:
            rows = [row for row in rows if needle in row.name.casefold()]

        suggested_count = 0
        self._updating_table = True
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            for row_idx, item in enumerate(rows):
                self.table.setItem(
                    row_idx, 0, self._read_only_item(self._part_label(item.part))
                )
                self.table.setItem(
                    row_idx, 1, self._read_only_item(pending_full_name_label(item))
                )
                name_item = self._read_only_item(item.name)
                name_item.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row_idx, 2, name_item)

                suggestion = suggest_korean_name(item.part, item.name)
                korean_item = QTableWidgetItem(suggestion)
                if suggestion:
                    suggested_count += 1
                    korean_item.setData(SUGGESTION_ROLE, suggestion)
                    self._style_korean_cell(korean_item, is_recommendation=True)
                self.table.setItem(row_idx, 3, korean_item)
                self.table.setItem(row_idx, 4, self._read_only_item(item.source or "-"))
        finally:
            self.table.blockSignals(False)
            self._updating_table = False

        summary = f"한글 표기 필요: {self._store.pending_count():,}건"
        if suggested_count:
            summary += f" · 추천 {suggested_count:,}건"
        if needle:
            summary += f" · 표시 {len(rows):,}건"
        self.summary_label.setText(summary)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table or item.column() != 3:
            return
        suggestion = item.data(SUGGESTION_ROLE)
        text = item.text().strip()
        if not text:
            item.setToolTip("")
            item.setForeground(QColor(TEXT_PRIMARY))
            return
        is_recommendation = bool(suggestion and text == suggestion)
        self._style_korean_cell(item, is_recommendation=is_recommendation)

    @staticmethod
    def _style_korean_cell(item: QTableWidgetItem, *, is_recommendation: bool) -> None:
        if is_recommendation:
            item.setForeground(QColor(TEXT_MUTED))
            item.setToolTip(
                "자동 추천 표기입니다. 수정·삭제하지 않고 저장하면 매핑에 반영됩니다."
            )
        else:
            item.setForeground(QColor(TEXT_PRIMARY))
            item.setToolTip("직접 입력한 표기입니다.")

    @staticmethod
    def _part_label(part: str) -> str:
        return "성" if part == "last" else "이름"

    @staticmethod
    def _read_only_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _save_entries(self) -> None:
        self._store = KoreanNameStore.load()
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
