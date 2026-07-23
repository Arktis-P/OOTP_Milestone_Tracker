"""Dialog for inspecting boxscore import errors."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from core.i18n import tr
from core.stats.models import ImportResult
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box, table_card


def import_error_row_text(error: ImportResult) -> str:
    game_id = str(error.game_id) if error.game_id else tr("Unknown")
    message = error.error or tr("Unknown error")
    return f"{game_id}\t{message}"


def import_errors_to_clipboard_text(errors: list[ImportResult]) -> str:
    return "\n".join(import_error_row_text(error) for error in errors)


class ImportErrorsDialog(QDialog):
    def __init__(
        self,
        errors: list[ImportResult],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._errors = list(errors)
        self.setWindowTitle(tr("Import Errors"))
        self.resize(*scale_size(680, 420))

        self.table = QTableWidget(len(self._errors), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("#"), tr("Game ID"), tr("Error Message")]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        for row_idx, error in enumerate(self._errors):
            game_id = str(error.game_id) if error.game_id else tr("Unknown")
            message = error.error or tr("Unknown error")
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(row_idx + 1)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(game_id))
            self.table.setItem(row_idx, 2, QTableWidgetItem(message))
        self.table.resizeColumnsToContents()

        buttons = make_button_box(close=True, cancel=False)
        copy_selected = QPushButton(tr("Copy Selected"))
        copy_all = QPushButton(tr("Copy All"))
        buttons.addButton(copy_selected, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(copy_all, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        copy_selected.clicked.connect(self.copy_selected)
        copy_all.clicked.connect(self.copy_all)

        layout = init_dialog_layout(self)
        layout.addWidget(
            table_card(
                tr("{count} import error(s)").format(count=len(self._errors)),
                self.table,
            ),
            stretch=1,
        )
        add_dialog_footer(layout, buttons)

    def selected_errors(self) -> list[ImportResult]:
        rows = sorted(
            {
                index.row()
                for index in self.table.selectionModel().selectedRows()
                if 0 <= index.row() < len(self._errors)
            }
        )
        return [self._errors[row] for row in rows]

    def copy_selected(self) -> None:
        selected = self.selected_errors()
        if selected:
            QApplication.clipboard().setText(import_errors_to_clipboard_text(selected))

    def copy_all(self) -> None:
        QApplication.clipboard().setText(import_errors_to_clipboard_text(self._errors))
