"""Open files with the OS default application."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def open_path_in_default_app(path: str | Path) -> bool:
    """Open a file or folder with the platform default handler."""
    target = Path(path)
    if not target.exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
