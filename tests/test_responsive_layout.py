from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from gui.widgets.responsive_flow import CollapsibleSection, ResponsiveFlowLayout


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _container_with_buttons() -> tuple[QWidget, ResponsiveFlowLayout, list[QPushButton]]:
    container = QWidget()
    layout = ResponsiveFlowLayout(container, horizontal_spacing=8, vertical_spacing=8)
    buttons: list[QPushButton] = []
    for index in range(6):
        button = QPushButton(f"Filter {index + 1}")
        button.setFixedSize(200, 32)
        layout.addWidget(button)
        buttons.append(button)
    container.setLayout(layout)
    return container, layout, buttons


def test_flow_layout_keeps_controls_on_one_row_at_target_widths() -> None:
    app = qapp()
    container, layout, buttons = _container_with_buttons()

    for width in (1650, 1366):
        container.resize(width, 120)
        layout.setGeometry(container.rect())
        app.processEvents()

        rows = {button.geometry().y() for button in buttons}
        assert len(rows) == 1
        assert layout.heightForWidth(width) <= 40


def test_flow_layout_wraps_at_minimum_width_without_horizontal_overflow() -> None:
    app = qapp()
    container, layout, buttons = _container_with_buttons()
    minimum_width = 420

    container.resize(minimum_width, 240)
    layout.setGeometry(container.rect())
    app.processEvents()

    rows = {button.geometry().y() for button in buttons}
    assert len(rows) >= 3
    assert layout.heightForWidth(minimum_width) > layout.heightForWidth(1366)
    assert all(button.geometry().right() <= minimum_width for button in buttons)


def test_collapsible_section_hides_and_restores_secondary_content() -> None:
    app = qapp()
    content = QPushButton("Advanced filter")
    section = CollapsibleSection("Advanced filters", content, expanded=False)
    section.show()
    app.processEvents()

    assert not section.is_expanded()
    assert not content.isVisible()
    assert section.toggle_button.accessibleName() == "Advanced filters"

    section.set_expanded(True)
    app.processEvents()

    assert section.is_expanded()
    assert content.isVisible()

