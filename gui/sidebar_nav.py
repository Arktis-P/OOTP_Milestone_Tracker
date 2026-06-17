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

from gui.theme import EMERALD_400, EMERALD_500, EMERALD_950, SLATE_400, SLATE_500, SLATE_800, SLATE_950

_NAV_SECTIONS: list[tuple[str | None, list[tuple[int, str, str]]]] = [
    (
        "기록 검사기",
        [
            (0, "📊", "대시보드"),
            (1, "🏆", "마일스톤 기록"),
            (2, "👤", "선수 기록"),
            (3, "🔮", "마일스톤 예측"),
        ],
    ),
    (
        "도구 및 설정",
        [
            (4, "📂", "초기값 설정"),
            (5, "✍️", "레이팅 편집"),
            (6, "⚙️", "설정"),
        ],
    ),
]

_BTN_ACTIVE = (
    f"QPushButton#navBtnActive {{"
    f"  background-color: {EMERALD_950};"
    f"  color: {EMERALD_400};"
    f"  border: none;"
    f"  border-left: 4px solid {EMERALD_500};"
    f"  border-radius: 8px;"
    f"  text-align: left;"
    f"  padding: 8px 10px;"
    f"  font-weight: 600;"
    f"}}"
)
_BTN_IDLE = (
    f"QPushButton#navBtnIdle {{"
    f"  background-color: transparent;"
    f"  color: {SLATE_400};"
    f"  border: none;"
    f"  border-left: 4px solid transparent;"
    f"  border-radius: 8px;"
    f"  text-align: left;"
    f"  padding: 8px 10px;"
    f"}}"
    f"QPushButton#navBtnIdle:hover {{"
    f"  background-color: {SLATE_950};"
    f"  color: #e2e8f0;"
    f"}}"
)


class SidebarNav(QWidget):
    """Vertical nav with section headers and page index signals."""

    page_changed = pyqtSignal(int)

    SETUP_PAGE_INDEX = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarNav")
        self.setFixedWidth(200)
        self.setStyleSheet(
            f"QWidget#sidebarNav {{"
            f"  background-color: {SLATE_950};"
            f"  border-right: 1px solid {SLATE_800};"
            f"}}"
        )

        self._buttons: dict[int, QPushButton] = {}
        self._setup_badge: QLabel | None = None
        self._active_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(2)

        for section_title, items in _NAV_SECTIONS:
            if section_title:
                if root.count() > 0:
                    line = QFrame()
                    line.setFrameShape(QFrame.Shape.HLine)
                    line.setStyleSheet(f"color: {SLATE_800};")
                    root.addWidget(line)
                    root.addSpacing(4)
                header = QLabel(section_title.upper())
                header.setStyleSheet(
                    f"color: {SLATE_500}; font-size: 10px; font-weight: 700;"
                    "letter-spacing: 0.05em; padding: 4px 8px;"
                )
                root.addWidget(header)

            for index, icon, label in items:
                btn = QPushButton(f"  {icon}  {label}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFlat(True)
                btn.clicked.connect(lambda _checked=False, i=index: self.set_current_index(i))
                self._buttons[index] = btn

                if index == self.SETUP_PAGE_INDEX:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    row_layout.addWidget(btn, stretch=1)
                    self._setup_badge = QLabel("●")
                    self._setup_badge.setStyleSheet("color: #ef4444; font-size: 10px;")
                    self._setup_badge.setVisible(False)
                    self._setup_badge.setToolTip("받을 수 있는 기준 파일 업데이트")
                    row_layout.addWidget(self._setup_badge)
                    root.addWidget(row)
                else:
                    root.addWidget(btn)

        root.addStretch()

        footer = QFrame()
        footer.setStyleSheet(
            f"background-color: #0f172a99; border: 1px solid {SLATE_800};"
            "border-radius: 8px; padding: 6px;"
        )
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        footer_layout.setSpacing(2)
        cap = QLabel("배포 정보")
        cap.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        store = QLabel("%APPDATA% 저장")
        store.setStyleSheet(f"color: {EMERALD_400}; font-size: 11px; font-weight: 700;")
        store.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("SQLite DB 연동")
        sub.setStyleSheet(f"color: {SLATE_400}; font-size: 9px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(cap)
        footer_layout.addWidget(store)
        footer_layout.addWidget(sub)
        root.addWidget(footer)

        self.setStyleSheet(self.styleSheet() + _BTN_ACTIVE + _BTN_IDLE)
        self.set_current_index(0, emit=False)

    def set_current_index(self, index: int, *, emit: bool = True) -> None:
        if index not in self._buttons:
            return
        self._active_index = index
        for i, btn in self._buttons.items():
            btn.setObjectName("navBtnActive" if i == index else "navBtnIdle")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if emit:
            self.page_changed.emit(index)

    def current_index(self) -> int:
        return self._active_index

    def set_setup_badge_visible(self, visible: bool, tooltip: str = "") -> None:
        if self._setup_badge is None:
            return
        self._setup_badge.setVisible(visible)
        if tooltip:
            self._setup_badge.setToolTip(tooltip)
            setup_btn = self._buttons.get(self.SETUP_PAGE_INDEX)
            if setup_btn is not None:
                setup_btn.setToolTip(tooltip if visible else "")
