"""Review UI for parsed OOTP news messages before database writes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import fields, is_dataclass
from datetime import date
from typing import Any

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.milestone.message_automation.parser import ParsedMessage
from gui.widgets.card_panel import CardPanel
from gui.widgets.message_review_model import (
    STATUS_APPLIED,
    STATUS_APPROVED,
    STATUS_CANDIDATE,
    STATUS_DATE_NEEDED,
    STATUS_ERROR,
    STATUS_EXCLUDED,
    MessageReviewItem,
    MessageReviewModel,
    editable_form_values,
)


SaveCallback = Callable[[list[ParsedMessage]], Any]
ReanalyzeCallback = Callable[[MessageReviewItem], ParsedMessage]


class MessageReviewView(QWidget):
    """Standalone preview/approval screen for message automation results."""

    review_changed = pyqtSignal()
    save_completed = pyqtSignal(object)
    reanalysis_requested = pyqtSignal(str)

    def __init__(
        self,
        items: Iterable[MessageReviewItem] = (),
        *,
        save_callback: SaveCallback | None = None,
        reanalyze_callback: ReanalyzeCallback | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("messageReviewView")
        self.model = MessageReviewModel(items)
        self._save_callback = save_callback
        self._reanalyze_callback = reanalyze_callback
        self._selected_row = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title = QLabel(tr("News Message Review"))
        title.setObjectName("pageTitle")
        root.addWidget(title)

        intro = QLabel(
            tr(
                "Review parsed messages and approve candidate records before saving. "
                "The save callback is only called for approved rows."
            )
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("messageReviewSummary")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        actions = QHBoxLayout()
        self.approve_button = QPushButton(tr("Approve selected"))
        self.approve_all_button = QPushButton(tr("Approve all candidates"))
        self.exclude_button = QPushButton(tr("Exclude selected"))
        self.edit_button = QPushButton(tr("Edit extracted result"))
        self.reanalyze_button = QPushButton(tr("Reanalyze selected"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.assign_date_button = QPushButton(tr("Apply date to selected"))
        self.save_button = QPushButton(tr("Save approved records"))

        for widget in (
            self.approve_button,
            self.approve_all_button,
            self.exclude_button,
            self.edit_button,
            self.reanalyze_button,
            self.date_edit,
            self.assign_date_button,
            self.save_button,
        ):
            actions.addWidget(widget)
        actions.addStretch()
        root.addLayout(actions)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("messageReviewTable")
        self.table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Message title"),
                tr("Type"),
                tr("Player/Team"),
                tr("Status"),
                tr("Planned records"),
                tr("Reason"),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.raw_text = QPlainTextEdit()
        self.raw_text.setObjectName("messageReviewRawText")
        self.raw_text.setReadOnly(True)
        self.extracted_text = QPlainTextEdit()
        self.extracted_text.setObjectName("messageReviewExtractedText")
        self.extracted_text.setReadOnly(True)

        detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        detail_splitter.addWidget(_text_card(tr("Original message"), self.raw_text))
        detail_splitter.addWidget(_text_card(tr("Extracted result"), self.extracted_text))
        detail_splitter.setSizes([1, 1])

        table_card = CardPanel(tr("Parsed messages"))
        table_card.add_widget(self.table)
        root.addWidget(table_card, stretch=3)
        root.addWidget(detail_splitter, stretch=2)

        self.approve_button.clicked.connect(self.approve_selected)
        self.approve_all_button.clicked.connect(self.approve_all)
        self.exclude_button.clicked.connect(self.exclude_selected)
        self.edit_button.clicked.connect(self.edit_selected_extracted_result)
        self.reanalyze_button.clicked.connect(self.reanalyze_selected)
        self.assign_date_button.clicked.connect(self.assign_date_to_selected)
        self.save_button.clicked.connect(self.save_approved)

        self.refresh()

    def set_items(self, items: Iterable[MessageReviewItem]) -> None:
        self.model.set_items(items)
        self._selected_row = -1
        self.refresh()

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def approve_selected(self) -> int:
        changed = self.model.approve(self.selected_rows())
        self.refresh()
        return changed

    def approve_all(self) -> int:
        changed = self.model.approve_all_candidates()
        self.refresh()
        return changed

    def exclude_selected(self) -> int:
        changed = self.model.exclude(self.selected_rows())
        self.refresh()
        return changed

    def apply_extracted_edits(
        self,
        row: int,
        values: dict[str, str],
        *,
        form_index: int = 0,
    ) -> bool:
        if not (0 <= row < len(self.model)):
            return False
        self.model.update_form_fields(row, form_index, values)
        self._selected_row = row
        self.refresh()
        return self.model[row].status != STATUS_ERROR

    def edit_selected_extracted_result(self) -> bool:
        rows = self.selected_rows()
        if len(rows) != 1:
            return False
        row = rows[0]
        if not (0 <= row < len(self.model)):
            return False
        item = self.model[row]
        if not item.parsed.forms:
            return False
        dialog = ExtractedResultEditDialog(item, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.apply_extracted_edits(
            row,
            dialog.edited_values(),
            form_index=dialog.selected_form_index(),
        )

    def assign_date_to_selected(self) -> int:
        qdate = self.date_edit.date()
        changed = self.model.assign_date(
            self.selected_rows(),
            date(qdate.year(), qdate.month(), qdate.day()),
        )
        self.refresh()
        return changed

    def reanalyze_selected(self) -> int:
        rows = self.selected_rows()
        changed = 0
        for row in rows:
            if not (0 <= row < len(self.model)):
                continue
            item = self.model[row]
            self.reanalysis_requested.emit(item.source_id)
            if self._reanalyze_callback is None:
                continue
            try:
                parsed = self._reanalyze_callback(item)
            except Exception as exc:  # pragma: no cover - defensive UI path
                self.model.mark_error(row, str(exc))
            else:
                self.model.update_parsed(row, parsed)
                changed += 1
        self.refresh()
        return changed

    def save_approved(self) -> Any:
        approved = self.model.approved_items()
        if not approved:
            self.refresh()
            return None
        if self._save_callback is None:
            return None
        result = self._save_callback([item.parsed for item in approved])
        self.model.mark_applied(approved, result)
        self.save_completed.emit(result)
        self.refresh()
        return result

    def refresh(self) -> None:
        self._populate_table()
        self._update_summary()
        self._restore_or_show_selection()
        self._update_button_state()
        self.review_changed.emit()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.model))
        for row, item in enumerate(self.model.items):
            values = [
                item.message_date.isoformat() if item.message_date else "",
                item.title,
                item.category,
                _subject_text(item),
                _status_label(item.status or ""),
                str(item.generated_count),
                item.reason,
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, table_item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _update_summary(self) -> None:
        counts = self.model.summary_counts()
        self.summary_label.setText(
            tr(
                "Total {total} | Candidates {candidates} | Approved {approved} | "
                "Applied {applied} | Excluded {excluded} | Date needed {date_needed} | Errors {errors}"
            ).format(**counts)
        )

    def _restore_or_show_selection(self) -> None:
        row = self._selected_row
        if not (0 <= row < len(self.model)):
            row = 0 if len(self.model) else -1
        if row >= 0 and not self.table.selectedIndexes():
            self.table.selectRow(row)
        self._show_detail(row)

    def _on_selection_changed(self) -> None:
        rows = self.selected_rows()
        self._selected_row = rows[0] if rows else -1
        self._show_detail(self._selected_row)
        self._update_button_state()

    def _show_detail(self, row: int) -> None:
        if not (0 <= row < len(self.model)):
            self.raw_text.clear()
            self.extracted_text.clear()
            return
        item = self.model[row]
        self.raw_text.setPlainText(item.raw_text)
        self.extracted_text.setPlainText(_extracted_text(item))

    def _update_button_state(self) -> None:
        selected = [self.model[row] for row in self.selected_rows() if 0 <= row < len(self.model)]
        self.approve_button.setEnabled(any(item.can_approve() for item in selected))
        self.exclude_button.setEnabled(any(item.status not in (STATUS_APPLIED, STATUS_ERROR) for item in selected))
        self.edit_button.setEnabled(len(selected) == 1 and bool(selected[0].parsed.forms))
        self.reanalyze_button.setEnabled(bool(selected))
        self.assign_date_button.setEnabled(any(item.status == STATUS_DATE_NEEDED for item in selected))
        self.approve_all_button.setEnabled(any(item.can_approve() for item in self.model.items))
        self.save_button.setEnabled(bool(self.model.approved_items()) and self._save_callback is not None)


def _text_card(title: str, editor: QPlainTextEdit) -> CardPanel:
    card = CardPanel(title)
    card.add_widget(editor)
    return card


class ExtractedResultEditDialog(QDialog):
    """Small field table for correcting one extracted dataclass form."""

    def __init__(self, item: MessageReviewItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(tr("Edit extracted result"))
        self.resize(760, 620)

        self.form_combo = QComboBox()
        for index, form in enumerate(item.parsed.forms):
            self.form_combo.addItem(f"{index + 1}. {type(form).__name__}", index)
        self.form_combo.currentIndexChanged.connect(self._load_selected_form)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Field"), tr("Value")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        hint = QLabel(
            tr("Edit parsed values before approval. Dates must use YYYY-MM-DD.")
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.form_combo)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.buttons)
        self._load_selected_form()

    def selected_form_index(self) -> int:
        data = self.form_combo.currentData()
        return int(data) if data is not None else 0

    def edited_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            field_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if field_item is None:
                continue
            values[field_item.text()] = value_item.text() if value_item is not None else ""
        return values

    def _load_selected_form(self) -> None:
        index = self.selected_form_index()
        form = self.item.parsed.forms[index]
        values = editable_form_values(form)
        self.table.setRowCount(len(values))
        for row, (key, value) in enumerate(values.items()):
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, QTableWidgetItem(value))


def _status_label(status: str) -> str:
    labels = {
        STATUS_CANDIDATE: tr("Candidate"),
        STATUS_APPROVED: tr("Approved"),
        STATUS_APPLIED: tr("Applied"),
        STATUS_EXCLUDED: tr("Excluded"),
        STATUS_DATE_NEEDED: tr("Date needed"),
        STATUS_ERROR: tr("Error"),
    }
    return labels.get(status, status)


def _subject_text(item: MessageReviewItem) -> str:
    names = sorted(set(item.parsed.player_names.values()))
    if names:
        return ", ".join(names[:3]) + ("..." if len(names) > 3 else "")
    subjects: list[str] = []
    for form in item.parsed.forms:
        for attr in ("player_name", "joining_players", "leaving_players", "team", "join_team"):
            value = str(getattr(form, attr, "") or "").strip()
            if value:
                subjects.append(value)
                break
    return ", ".join(subjects[:3])


def _extracted_text(item: MessageReviewItem) -> str:
    lines = [
        f"Source: {item.source_id}",
        f"Title: {item.title}",
        f"Type: {item.category}",
        f"Status: {_status_label(item.status or '')}",
        f"Planned records: {item.generated_count}",
    ]
    if item.reason:
        lines.append(f"Reason: {item.reason}")
    if item.created_record_ids:
        lines.append("Created record IDs: " + ", ".join(str(value) for value in item.created_record_ids))
    if item.parsed.forms:
        lines.append("")
        lines.append("Forms")
    for index, form in enumerate(item.parsed.forms, start=1):
        lines.append(f"[{index}] {type(form).__name__}")
        for key, value in _form_values(form).items():
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _form_values(form: Any) -> dict[str, Any]:
    if is_dataclass(form):
        return {field.name: getattr(form, field.name) for field in fields(form)}
    return {
        key: value
        for key, value in vars(form).items()
        if not key.startswith("_")
    }
