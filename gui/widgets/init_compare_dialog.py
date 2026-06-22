"""Dialog showing stat differences between file export and boxscore DB."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
)

from core.i18n import tr
from core.stats.initial_import import StatDiff
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import init_dialog_layout, make_button_box, muted_label, table_card


class InitCompareDialog(QDialog):
    def __init__(
        self,
        title: str,
        diffs: list[StatDiff],
        *,
        allow_save: bool,
        save_label: str = "Update based on file",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*scale_size(640, 420))
        self._save_confirmed = False

        if diffs:
            table = QTableWidget(len(diffs), 5)
            table.setHorizontalHeaderLabels(
                [tr("Player"), tr("Stat"), tr("Boxscore Total"), tr("File Value"), tr("Diff")]
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

        note = muted_label(
            tr("No differences.") if not diffs
            else tr("File may contain games not yet in boxscore DB.")
        )

        if allow_save:
            buttons = make_button_box(
                cancel=True,
                custom_accept=(save_label, QDialogButtonBox.ButtonRole.AcceptRole),
            )
            buttons.accepted.connect(self._confirm_save)
            buttons.rejected.connect(self.reject)
        else:
            buttons = make_button_box(ok=True)
            buttons.accepted.connect(self.accept)

        layout = init_dialog_layout(self)
        if table is not None:
            layout.addWidget(table_card(tr("Stat Differences"), table), stretch=1)
        layout.addWidget(note)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def _confirm_save(self) -> None:
        self._save_confirmed = True
        self.accept()

    @property
    def save_confirmed(self) -> bool:
        return self._save_confirmed
