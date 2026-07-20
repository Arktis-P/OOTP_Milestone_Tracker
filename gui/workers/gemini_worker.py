"""Background worker for Gemini Korean-name translation requests."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.roster.gemini_korean import (
    GeminiDiagnostic,
    GeminiTranslationResult,
    NamePart,
    diagnose_gemini,
    translate_names_with_gemini,
)


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
        *,
        model_preference: str = "gemini-3.5-flash",
    ) -> None:
        super().__init__(parent)
        self.api_key = api_key
        self.items = items
        self.model_preference = model_preference

    def cancel(self) -> None:
        """Request cancellation at the next safe network/retry boundary."""
        self.requestInterruption()

    def run(self) -> None:
        try:
            result: GeminiTranslationResult = translate_names_with_gemini(
                self.api_key,
                self.items,
                on_status=lambda text: self.status.emit(text),
                should_cancel=self.isInterruptionRequested,
                model_preference=self.model_preference,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class GeminiDiagnosticWorker(QThread):
    """Run the explicit model-access diagnostic away from the UI thread."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        parent=None,
        *,
        model_preference: str = "gemini-3.5-flash",
    ) -> None:
        super().__init__(parent)
        self.api_key = api_key
        self.model_preference = model_preference

    def run(self) -> None:
        try:
            result: GeminiDiagnostic = diagnose_gemini(
                self.api_key, model_preference=self.model_preference
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
