"""Background worker for Gemini Korean-name translation requests."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.roster.gemini_korean import NamePart, translate_names_via_gemini


class GeminiTranslateWorker(QThread):
    """Runs a Gemini translation request off the UI thread."""

    finished = pyqtSignal(object)
    status = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        items: list[tuple[NamePart, str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api_key = api_key
        self.items = items

    def run(self) -> None:
        try:
            results = translate_names_via_gemini(
                self.api_key,
                self.items,
                on_status=lambda text: self.status.emit(text),
            )
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
