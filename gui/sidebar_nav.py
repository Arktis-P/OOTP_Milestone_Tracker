"""Sidebar navigation matching the HTML prototype layout."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from gui.theme import (
    AMBER_TEXT,
    BG_PANEL,
    BORDER,
    GREEN_TEXT,
    RED_TEXT,
    TEXT_MUTED,
    TEXT_SECONDARY,
)


def _nav_sections() -> list[tuple[str | None, list[tuple[int, str, str]]]]:
    return [
        (
            tr("Record Inspector"),
            [
                (0, "📊", tr("Dashboard")),
                (1, "🏆", tr("Achievement Records")),
                (2, "👤", tr("Player Stats")),
                (3, "🔮", tr("Achievement Predictions")),
            ],
        ),
        (
            tr("Tools & Settings"),
            [
                (4, "📂", tr("Import Existing Records")),
                (5, "✍️", tr("Rating Editor")),
                (6, "⚙️", tr("Settings")),
            ],
        ),
    ]


class SidebarNav(QWidget):
    """Vertical nav with section headers and page index signals."""

    page_changed = pyqtSignal(int)

    SETUP_PAGE_INDEX = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarNav")
        self.setMinimumWidth(200)
        self.setAccessibleName(tr("Main navigation"))
        self.setAccessibleDescription(
            tr("Use Tab to move through navigation items and Space or Enter to open a page.")
        )

        self._buttons: dict[int, QPushButton] = {}
        self._setup_badge: QLabel | None = None
        self._active_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(2)

        for section_title, items in _nav_sections():
            if section_title:
                if root.count() > 0:
                    line = QFrame()
                    line.setFrameShape(QFrame.Shape.HLine)
                    line.setStyleSheet(f"color: {BORDER};")
                    root.addWidget(line)
                    root.addSpacing(4)
                header = QLabel(section_title.upper())
                header.setObjectName("sectionTitle")
                header.setAccessibleName(section_title)
                header.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700;"
                    "letter-spacing: 0.05em; padding: 4px 8px;"
                )
                root.addWidget(header)

            for index, icon, label in items:
                btn = QPushButton(f"  {icon}  {label}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFlat(True)
                btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                btn.setAccessibleName(label)
                btn.setAccessibleDescription(
                    tr("Navigation item. Press Space or Enter to open {page}.").format(
                        page=label
                    )
                )
                btn.clicked.connect(lambda _checked=False, i=index: self.set_current_index(i))
                self._buttons[index] = btn

                if index == self.SETUP_PAGE_INDEX:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    row_layout.addWidget(btn, stretch=1)
                    self._setup_badge = QLabel("●")
                    self._setup_badge.setObjectName("warningText")
                    self._setup_badge.setAccessibleName(tr("Bundle update available"))
                    self._setup_badge.setStyleSheet("color: #f14c4c; font-size: 10px;")
                    self._setup_badge.setVisible(False)
                    self._setup_badge.setToolTip(tr("Bundle update available"))
                    row_layout.addWidget(self._setup_badge)
                    root.addWidget(row)
                else:
                    root.addWidget(btn)

        root.addStretch()

        footer = QFrame()
        footer.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        footer_layout.setSpacing(2)
        self._status_line = QLabel(tr("● Checking data..."))
        self._status_line.setObjectName("statusText")
        self._status_line.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 700;")
        self._status_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._context_line = QLabel("")
        self._context_line.setObjectName("helperText")
        self._context_line.setWordWrap(True)
        self._context_line.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px;")
        self._context_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(self._status_line)
        footer_layout.addWidget(self._context_line)
        footer.setToolTip("")
        self._footer = footer
        self._footer.setAccessibleName(tr("Data readiness status"))
        root.addWidget(footer)

        self.set_current_index(0, emit=False)

    def set_current_index(self, index: int, *, emit: bool = True) -> None:
        if index not in self._buttons:
            return
        self._active_index = index
        for i, btn in self._buttons.items():
            btn.setObjectName("navBtnActive" if i == index else "navBtnIdle")
            btn.setAccessibleDescription(
                tr("{state}. Press Space or Enter to open {page}.").format(
                    state=tr("Selected") if i == index else tr("Not selected"),
                    page=btn.accessibleName(),
                )
            )
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if emit:
            self.page_changed.emit(index)

    def current_index(self) -> int:
        return self._active_index

    _STATUS_COLORS = {"ok": GREEN_TEXT, "warning": AMBER_TEXT, "error": RED_TEXT}

    def set_status(
        self,
        *,
        level: str,
        status_text: str,
        context_text: str,
        tooltip: str = "",
    ) -> None:
        color = self._STATUS_COLORS.get(level, TEXT_SECONDARY)
        self._status_line.setText(status_text)
        self._status_line.setAccessibleName(tr("{level} status").format(level=level))
        self._status_line.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")
        self._context_line.setText(context_text)
        self._footer.setAccessibleDescription(
            tr("{level} status: {status}. {context}").format(
                level=level, status=status_text, context=context_text
            )
        )
        self._footer.setToolTip(tooltip)

    def set_setup_badge_visible(self, visible: bool, tooltip: str = "") -> None:
        if self._setup_badge is None:
            return
        self._setup_badge.setVisible(visible)
        if tooltip:
            self._setup_badge.setToolTip(tooltip)
            setup_btn = self._buttons.get(self.SETUP_PAGE_INDEX)
            if setup_btn is not None:
                setup_btn.setToolTip(tooltip if visible else "")
