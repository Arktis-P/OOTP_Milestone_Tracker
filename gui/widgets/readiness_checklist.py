"""Dashboard "getting started" checklist — auto-collapses once everything is ready."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.app_state import ReadinessItem
from core.i18n import tr
from gui.theme import GREEN_TEXT, TEXT_SECONDARY, hint_style
from gui.widgets.card_panel import CardPanel

_ACTION_LABELS = {
    "league": tr("Select League →"),
    "teams": tr("Select League →"),
    "init_import": tr("Import Existing Records →"),
    "boxscore_import": tr("Import Boxscores →"),
}


class ReadinessChecklistCard(QWidget):
    """Shows 4 setup steps with action buttons; collapses to one line when all done."""

    action_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._card = CardPanel(tr("Getting Started"))
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(6)
        self._card.content_layout.addLayout(self._rows_layout)

        self._collapsed_chip = QFrame()
        self._collapsed_chip.setObjectName("readinessCompleteChip")
        self._collapsed_chip.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        chip_layout = QHBoxLayout(self._collapsed_chip)
        chip_layout.setContentsMargins(12, 6, 12, 6)
        chip_layout.setSpacing(6)
        chip_layout.addStretch()
        self._collapsed_label = QLabel(tr("✅ Setup complete"))
        self._collapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_label.setStyleSheet(
            f"color: {GREEN_TEXT}; font-weight: 650; font-size: 12px;"
        )
        chip_layout.addWidget(self._collapsed_label)
        chip_layout.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card)
        layout.addWidget(
            self._collapsed_chip,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        self._collapsed_chip.setVisible(False)

    def set_items(self, items: list[ReadinessItem]) -> None:
        while self._rows_layout.count():
            child = self._rows_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        all_done = all(item.done for item in items)
        self._card.setVisible(not all_done)
        self._collapsed_chip.setVisible(all_done)
        if all_done:
            return

        for item in items:
            self._rows_layout.addWidget(self._build_row(item))

    def _build_row(self, item: ReadinessItem) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        icon = QLabel("✅" if item.done else "⚠️")
        icon.setFixedWidth(20)
        row_layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title = QLabel(item.title)
        if item.done:
            title.setStyleSheet(f"color: {GREEN_TEXT}; font-weight: 600;")
        else:
            title.setStyleSheet("font-weight: 600;")
        detail = QLabel(item.detail)
        detail.setWordWrap(True)
        detail.setStyleSheet(hint_style(TEXT_SECONDARY))
        text_col.addWidget(title)
        text_col.addWidget(detail)
        row_layout.addLayout(text_col, stretch=1)

        if not item.done:
            action_btn = QPushButton(_ACTION_LABELS.get(item.key, tr("Go →")))
            action_btn.setObjectName("linkButton")
            action_btn.clicked.connect(
                lambda _checked=False, key=item.key: self.action_requested.emit(key)
            )
            row_layout.addWidget(action_btn)

        return row
