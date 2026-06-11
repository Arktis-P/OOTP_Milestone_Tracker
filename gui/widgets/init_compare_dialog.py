"""Dialog showing stat differences between file export and boxscore DB."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.stats.initial_import import StatDiff


class InitCompareDialog(QDialog):
    def __init__(
        self,
        title: str,
        diffs: list[StatDiff],
        *,
        allow_save: bool,
        save_label: str = "파일 기준으로 갱신",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 420)
        self._save_confirmed = False

        if diffs:
            table = QTableWidget(len(diffs), 5)
            table.setHorizontalHeaderLabels(
                ["선수", "항목", "박스스코어 집계", "파일값", "차이"]
            )
            for row_idx, item in enumerate(diffs):
                table.setItem(row_idx, 0, QTableWidgetItem(item.player_name))
                table.setItem(row_idx, 1, QTableWidgetItem(item.stat))
                table.setItem(row_idx, 2, QTableWidgetItem(str(item.db_value)))
                table.setItem(row_idx, 3, QTableWidgetItem(str(item.file_value)))
                diff_text = f"{item.diff:+.0f}" if item.diff == int(item.diff) else f"{item.diff:+.2f}"
                table.setItem(row_idx, 4, QTableWidgetItem(diff_text))
            table.resizeColumnsToContents()
        else:
            table = None

        note = QLabel(
            "차이가 없습니다." if not diffs else "박스스코어에 없는 경기가 파일에 포함됐을 수 있습니다."
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox()
        if allow_save:
            save_button = buttons.addButton(save_label, QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
            save_button.clicked.connect(self._confirm_save)
        else:
            buttons.addButton(QDialogButtonBox.StandardButton.Ok)
        buttons.rejected.connect(self.reject)
        if not allow_save:
            buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        if table:
            layout.addWidget(table)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _confirm_save(self) -> None:
        self._save_confirmed = True
        self.accept()

    @property
    def save_confirmed(self) -> bool:
        return self._save_confirmed
