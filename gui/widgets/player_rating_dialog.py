"""Dialog for editing a single player's roster ratings."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.roster.ootp_format import PlayerRow, player_display_name
from core.roster.position_filter import position_label
from core.roster.rating_fields import RATING_SECTIONS, RatingSection
from core.roster.row_access import RowField, row_get_field, row_set_field
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box
from gui.widgets.card_panel import CardPanel


class PlayerRatingDialog(QDialog):
    def __init__(
        self,
        row: PlayerRow,
        fieldnames: list[str],
        *,
        season_year: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._row = row
        self._fieldnames = fieldnames
        self._value_items: dict[tuple[str, int], QTableWidgetItem] = {}

        name = player_display_name(row, fieldnames)
        self.setWindowTitle(f"레이팅 편집 — {name}")
        self.resize(*scale_size(960, 620))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(8)

        for section in RATING_SECTIONS:
            group = QGroupBox(section.title)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(6, 8, 6, 6)
            group_layout.addWidget(self._build_section_table(section, row, fieldnames))
            body_layout.addWidget(group)

        scroll.setWidget(body)

        buttons = make_button_box(save=True, save_text="저장")
        buttons.accepted.connect(self._apply_and_accept)
        buttons.rejected.connect(self.reject)

        ratings_card = CardPanel("레이팅")
        ratings_card.add_widget(scroll)

        layout = init_dialog_layout(self)
        layout.addWidget(ratings_card, stretch=1)
        add_dialog_footer(layout, buttons)

    def _build_section_table(
        self,
        section: RatingSection,
        row: PlayerRow,
        fieldnames: list[str],
    ) -> QTableWidget:
        column_count = len(section.fields)
        table = QTableWidget(1, column_count)
        table.setHorizontalHeaderLabels(
            [field.display_label for field in section.fields]
        )
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed
            if not section.readonly
            else QTableWidget.EditTrigger.NoEditTriggers
        )

        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        for column_index in range(column_count):
            header.setSectionResizeMode(
                column_index, QHeaderView.ResizeMode.ResizeToContents
            )
            header_item = table.horizontalHeaderItem(column_index)
            if header_item is not None:
                header_item.setToolTip(section.fields[column_index].display_label)

        for column_index, field in enumerate(section.fields):
            value_text = self._format_value(section, field, row, fieldnames)
            value_item = QTableWidgetItem(value_text)
            value_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            )
            if section.readonly:
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(0, column_index, value_item)
            self._value_items[(field.name, field.occurrence)] = value_item

        row_height = table.verticalHeader().defaultSectionSize()
        frame = table.frameWidth() * 2
        table.setFixedHeight(table.horizontalHeader().height() + row_height + frame + 2)
        return table

    @staticmethod
    def _format_value(
        section: RatingSection,
        field: RowField,
        row: PlayerRow,
        fieldnames: list[str],
    ) -> str:
        value = row_get_field(row, fieldnames, field)
        if field.name == "Position" and section.readonly and value:
            return f"{position_label(value)} ({value})"
        return value

    def _apply_and_accept(self) -> None:
        for section in RATING_SECTIONS:
            if section.readonly:
                continue
            for field in section.fields:
                item = self._value_items[(field.name, field.occurrence)]
                row_set_field(
                    self._row,
                    self._fieldnames,
                    field,
                    item.text().strip(),
                )
        self.accept()
