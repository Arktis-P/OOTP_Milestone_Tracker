""""Enter one at a time" popup dialogs for manual milestone/award/transfer/injury entry.

These are thin wrappers around ``GuidedRecordEditor`` (see
``gui/widgets/guided_milestone_form.py``), the same typed editor used to
correct extracted records during message review, so both entry points share
identical fields, autocomplete, and validation. On accept, the built form
dataclass is available on `.form` (and `.milestone` for milestone/award).
"""

from __future__ import annotations

from typing import Literal

from PyQt6.QtWidgets import QDialog, QMessageBox, QWidget

from core.config import AppSettings
from core.i18n import tr
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    check_duplicate,
    parse_flexible_date,
)
from core.stats.aggregator import Aggregator
from gui.ui_compact import scale_size
from gui.widgets.app_dialog import add_dialog_footer, init_dialog_layout, make_button_box
from gui.widgets.guided_milestone_form import GuidedRecordEditor


class SingleMilestoneEntryDialog(QDialog):
    """One-at-a-time entry for a milestone or award record."""

    def __init__(
        self,
        category: Literal["milestone", "award"],
        aggregator: Aggregator,
        milestones: MilestoneDefinitions,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.milestones = milestones
        self.settings = settings
        self.category: Literal["milestone", "award"] = category
        self.form: ManualMilestoneFormData | None = None
        self.milestone: MilestoneDefinition | None = None
        self.setWindowTitle(tr("Add Award") if category == "award" else tr("Add Milestone"))
        self.resize(*scale_size(520, 560))

        self.editor = GuidedRecordEditor(aggregator, settings, milestones, parent=self)
        self.editor.set_record_type("milestone")
        self.editor.set_category(category)
        if initial_date:
            self._set_initial_date(initial_date)

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(self.editor, stretch=1)
        add_dialog_footer(outer, buttons)

    def _set_initial_date(self, initial_date: str) -> None:
        parsed = parse_flexible_date(initial_date)
        if parsed is not None:
            self.editor.set_initial_date(parsed)

    def _on_accept(self) -> None:
        errors = self.editor.validate()
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return

        form = self.editor.build_form_data()
        milestone = self.editor.selected_milestone()

        dup_kind, dup_msg = check_duplicate(self.aggregator.conn, form, milestone)
        if dup_kind == "warn":
            reply = QMessageBox.question(
                self,
                tr("Duplicate Check"),
                tr("{dup_msg}\nAdd anyway?").format(dup_msg=dup_msg),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.form = form
        self.milestone = milestone
        self.accept()


class SingleTransferEntryDialog(QDialog):
    """One-at-a-time entry for a player transfer/contract event."""

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.form: ManualTransferFormData | None = None
        self.setWindowTitle(tr("Add Team Move"))
        self.resize(*scale_size(520, 480))

        self.editor = GuidedRecordEditor(aggregator, settings, parent=self)
        self.editor.set_record_type("transfer")
        if initial_date:
            self._set_initial_date(initial_date)

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(self.editor, stretch=1)
        add_dialog_footer(outer, buttons)

    def _set_initial_date(self, initial_date: str) -> None:
        parsed = parse_flexible_date(initial_date)
        if parsed is not None:
            self.editor.set_initial_date(parsed)

    def _on_accept(self) -> None:
        errors = self.editor.validate()
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return
        self.form = self.editor.build_form_data()
        self.accept()


class SingleInjuryEntryDialog(QDialog):
    """One-at-a-time entry for a player injury/return event."""

    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        initial_date: str = "",
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.form: ManualInjuryFormData | None = None
        self.setWindowTitle(tr("Add Injury"))
        self.resize(*scale_size(480, 420))

        self.editor = GuidedRecordEditor(aggregator, settings, parent=self)
        self.editor.set_record_type("injury")
        if initial_date:
            self._set_initial_date(initial_date)

        buttons = make_button_box(save=True, save_text="Add")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = init_dialog_layout(self)
        outer.addWidget(self.editor, stretch=1)
        add_dialog_footer(outer, buttons)

    def _set_initial_date(self, initial_date: str) -> None:
        parsed = parse_flexible_date(initial_date)
        if parsed is not None:
            self.editor.set_initial_date(parsed)

    def _on_accept(self) -> None:
        errors = self.editor.validate()
        if errors:
            QMessageBox.warning(self, tr("Input Error"), "\n".join(errors))
            return
        self.form = self.editor.build_form_data()
        self.accept()
