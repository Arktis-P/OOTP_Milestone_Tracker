"""Layout sizing helpers — smaller windows and panels, not smaller fonts."""

from __future__ import annotations

from PyQt6.QtWidgets import QLayout, QWidget

# ~70% of the original 1100×720 main window (diagonal ratio).
MAIN_WINDOW_SIZE = (780, 520)
SETUP_WINDOW_SIZE = (560, 440)

# Original dialog design sizes; scale_size() shrinks window chrome only.
UI_SCALE = 0.7


def scale_size(width: int, height: int) -> tuple[int, int]:
    return max(320, round(width * UI_SCALE)), max(240, round(height * UI_SCALE))


def hint_style(color: str = "#64748b") -> str:
    return f"color: {color}; font-size: 12px;"


def compact_widget(
    widget: QWidget,
    *,
    margin: int = 6,
    spacing: int = 4,
) -> None:
    """Tighten root layout margins without changing fonts."""
    layout = widget.layout()
    if layout is None:
        return
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)


def compact_layout(layout: QLayout, *, margin: int | None = None, spacing: int = 4) -> None:
    if margin is not None:
        layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
