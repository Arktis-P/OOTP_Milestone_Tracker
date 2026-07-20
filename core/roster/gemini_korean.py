"""Resilient Gemini API integration for Korean name translation.

The Gemini model catalogue changes independently of the application.  This
module therefore discovers models for the configured API key before making a
translation request instead of assuming that a hard-coded model still exists.
It intentionally imports ``google-genai`` lazily: starting the desktop app
does not require a configured Gemini key, and tests never make live requests.
"""

from __future__ import annotations

import csv
import io
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal, Protocol

NamePart = Literal["last", "first"]

# These are preferences, not a substitute for discovery.  Only models returned
# by ``models.list`` and capable of generateContent are selected.
DEFAULT_MODEL_PREFERENCE = "gemini-3.5-flash"
_FALLBACK_MODEL_PREFERENCES = (
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
_REQUEST_TIMEOUT_MS = 20_000
_MAX_ATTEMPTS_PER_MODEL = 2
_RETRY_DELAYS_S = (0.5,)
_BATCH_SIZE = 40
_RETRYABLE_CATEGORIES = frozenset({"quota", "transient", "network", "timeout"})
_FALLBACK_CATEGORIES = _RETRYABLE_CATEGORIES | frozenset({"model_not_found"})
_API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_-]{16,}")

_PROMPT_HEADER = """Translate the following baseball-name parts to standard Korean transliteration.
`part` is either `last` (surname) or `first` (given name). Return only CSV with
the exact header `part,roman,korean`; do not add Markdown, explanations, or
rows that were not supplied. Preserve the supplied `part` and `roman` values.

Input CSV:
part,roman
"""


class _ClientFactory(Protocol):
    def __call__(self, api_key: str, http_options: Any) -> Any: ...


class GeminiServiceError(RuntimeError):
    """A safe, user-presentable Gemini failure with a stable category."""

    def __init__(self, category: str, detail: str = "") -> None:
        self.category = category
        self.detail = _redact(detail)
        super().__init__(_public_error_message(category, self.detail))


class GeminiCancelled(GeminiServiceError):
    def __init__(self) -> None:
        super().__init__("cancelled")


@dataclass(frozen=True)
class GeminiFailure:
    """A failed input batch.  Successful batches remain available."""

    item_count: int
    error: GeminiServiceError


@dataclass
class GeminiTranslationResult:
    translations: dict[tuple[NamePart, str], str] = field(default_factory=dict)
    failures: list[GeminiFailure] = field(default_factory=list)
    selected_models: tuple[str, ...] = ()
    cancelled: bool = False

    @property
    def is_partial(self) -> bool:
        return bool(self.translations) and (bool(self.failures) or self.cancelled)


@dataclass(frozen=True)
class GeminiDiagnostic:
    available_models: tuple[str, ...]
    selected_models: tuple[str, ...]


def translate_names_via_gemini(
    api_key: str,
    items: list[tuple[NamePart, str]],
    *,
    on_status: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    model_preference: str = DEFAULT_MODEL_PREFERENCE,
    client_factory: _ClientFactory | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[tuple[NamePart, str], str]:
    """Translate names and return all successful translations.

    This compatibility wrapper preserves the original dictionary API.  UI code
    that needs partial-failure detail should use ``translate_names_with_gemini``.
    """
    result = translate_names_with_gemini(
        api_key,
        items,
        on_status=on_status,
        should_cancel=should_cancel,
        model_preference=model_preference,
        client_factory=client_factory,
        sleep=sleep,
    )
    if not result.translations and result.cancelled:
        raise GeminiCancelled()
    if not result.translations and result.failures:
        raise result.failures[0].error
    return result.translations


def translate_names_with_gemini(
    api_key: str,
    items: list[tuple[NamePart, str]],
    *,
    on_status: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    model_preference: str = DEFAULT_MODEL_PREFERENCE,
    client_factory: _ClientFactory | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> GeminiTranslationResult:
    """Translate in bounded batches, retaining completed batches on failure."""
    _require_api_key(api_key)
    if not items:
        return GeminiTranslationResult()
    _raise_if_cancelled(should_cancel)

    client = _create_client(api_key, client_factory)
    diagnostic = diagnose_gemini_client(client, model_preference=model_preference)
    selected = diagnostic.selected_models
    if on_status:
        on_status(f"Gemini model selected: {selected[0]}")

    result = GeminiTranslationResult(selected_models=selected)
    for batch_number, batch in enumerate(_batches(items, _BATCH_SIZE), start=1):
        if _is_cancelled(should_cancel):
            result.cancelled = True
            break
        if on_status:
            on_status(f"Translating batch {batch_number} ({len(batch)} names)…")
        try:
            translated = _translate_batch(
                client,
                batch,
                selected,
                on_status=on_status,
                should_cancel=should_cancel,
                sleep=sleep,
            )
            result.translations.update(translated)
        except GeminiCancelled:
            result.cancelled = True
            break
        except GeminiServiceError as exc:
            result.failures.append(GeminiFailure(len(batch), exc))
            # Retrying further batches cannot repair credentials or a malformed
            # request, and it would needlessly consume quota.
            if exc.category in {"authentication", "authorization", "invalid_request"}:
                break
    return result


def diagnose_gemini(
    api_key: str,
    *,
    model_preference: str = DEFAULT_MODEL_PREFERENCE,
    client_factory: _ClientFactory | None = None,
) -> GeminiDiagnostic:
    """Explicit live diagnostic: validate access and report safe model choices.

    Call this only from a user-initiated diagnostic action.  It does not send a
    generation prompt and never returns or logs the API key.
    """
    _require_api_key(api_key)
    return diagnose_gemini_client(
        _create_client(api_key, client_factory), model_preference=model_preference
    )


def diagnose_gemini_client(client: Any, *, model_preference: str) -> GeminiDiagnostic:
    """Discover generateContent-capable models from an already-created client."""
    try:
        models = tuple(client.models.list())
    except Exception as exc:  # SDK exception types vary between releases.
        raise _as_service_error(exc) from exc

    available = tuple(
        name
        for model in models
        if (name := _model_name(model)) and _supports_generate_content(model)
    )
    selected = _select_models(available, model_preference)
    if not selected:
        raise GeminiServiceError("model_not_found")
    return GeminiDiagnostic(available_models=available, selected_models=selected)


def _translate_batch(
    client: Any,
    batch: list[tuple[NamePart, str]],
    models: Iterable[str],
    *,
    on_status: Callable[[str], None] | None,
    should_cancel: Callable[[], bool] | None,
    sleep: Callable[[float], None],
) -> dict[tuple[NamePart, str], str]:
    prompt = _build_prompt(batch)
    last_error: GeminiServiceError | None = None
    for model in models:
        for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
            _raise_if_cancelled(should_cancel)
            if on_status:
                suffix = "" if attempt == 0 else f", retry {attempt + 1}/{_MAX_ATTEMPTS_PER_MODEL}"
                on_status(f"Gemini request ({model}{suffix})…")
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                return _parse_gemini_response(response)
            except GeminiCancelled:
                raise
            except Exception as exc:
                error = _as_service_error(exc)
                last_error = error
                if error.category in _RETRYABLE_CATEGORIES and attempt < _MAX_ATTEMPTS_PER_MODEL - 1:
                    delay = _RETRY_DELAYS_S[attempt]
                    if on_status:
                        on_status(f"Gemini temporary issue; retrying in {delay:g}s…")
                    _sleep_with_cancellation(delay, should_cancel, sleep)
                    continue
                break
        if last_error is None or last_error.category not in _FALLBACK_CATEGORIES:
            break
        if on_status:
            on_status(f"Gemini fallback after {last_error.category}: trying next available model…")
    raise last_error or GeminiServiceError("unknown")


def _create_client(api_key: str, client_factory: _ClientFactory | None) -> Any:
    if client_factory is not None:
        return client_factory(api_key, _http_options())
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiServiceError("sdk_missing") from exc
    try:
        return genai.Client(api_key=api_key, http_options=_http_options())
    except GeminiServiceError:
        raise
    except Exception as exc:
        raise _as_service_error(exc) from exc


def _http_options() -> Any:
    """Construct stable-v1, bounded HTTP options when the SDK is installed."""
    try:
        from google.genai import types
    except ImportError:
        # Dependency injection in unit tests does not need SDK option objects.
        return {"api_version": "v1", "timeout": _REQUEST_TIMEOUT_MS}
    return types.HttpOptions(
        api_version="v1",
        timeout=_REQUEST_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(
            attempts=1,
            initial_delay=0.5,
            max_delay=1.0,
            http_status_codes=[429, 500, 502, 503, 504],
        ),
    )


def _build_prompt(items: list[tuple[NamePart, str]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for part, name in items:
        writer.writerow((part, name))
    return _PROMPT_HEADER + output.getvalue()


def _parse_gemini_response(response: Any) -> dict[tuple[NamePart, str], str]:
    text = _response_text(response)
    if not text:
        raise GeminiServiceError("malformed_response")
    parsed = _parse_csv_response(text)
    if not parsed:
        raise GeminiServiceError("malformed_response")
    return parsed


def _response_text(response: Any) -> str:
    if isinstance(response, dict):
        try:
            return str(response["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError):
            return ""
    text = getattr(response, "text", None)
    return text if isinstance(text, str) else ""


def _parse_csv_response(text: str) -> dict[tuple[NamePart, str], str]:
    result: dict[tuple[NamePart, str], str] = {}
    clean = "\n".join(
        line.strip() for line in text.strip().splitlines()
        if line.strip() and not line.strip().startswith("```")
    )
    for row in csv.reader(io.StringIO(clean)):
        if len(row) < 3:
            continue
        part, roman, korean = (row[0].strip().lower(), row[1].strip(), row[2].strip())
        if part in {"last", "first"} and roman and korean:
            result[(part, roman)] = korean  # type: ignore[index]
    return result


def _model_name(model: Any) -> str:
    name = model.get("name", "") if isinstance(model, dict) else getattr(model, "name", "")
    return str(name).removeprefix("models/").strip()


def _supports_generate_content(model: Any) -> bool:
    if isinstance(model, dict):
        actions = model.get("supported_actions") or model.get("supported_generation_methods")
    else:
        actions = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None)
    if not actions:
        # The SDK's model resource has changed field names; retain models with a
        # Gemini text-generation name rather than rejecting a valid model solely
        # because an older SDK omitted this optional metadata.
        return _model_name(model).startswith("gemini-")
    return any(str(action).replace("_", "").lower() == "generatecontent" for action in actions)


def _select_models(available: tuple[str, ...], model_preference: str) -> tuple[str, ...]:
    by_lower = {model.lower(): model for model in available}
    selected: list[str] = []
    for desired in (model_preference, *_FALLBACK_MODEL_PREFERENCES):
        model = by_lower.get(desired.strip().removeprefix("models/").lower())
        if model and model not in selected:
            selected.append(model)
    # Accounts may expose a newer supported Flash release not yet in the app's
    # preference list.  Use it before a non-Flash text model.
    for model in available:
        lowered = model.lower()
        if "flash" in lowered and "image" not in lowered and "live" not in lowered and model not in selected:
            selected.append(model)
    for model in available:
        if model not in selected and "image" not in model.lower() and "live" not in model.lower():
            selected.append(model)
    return tuple(selected)


def _as_service_error(exc: Exception) -> GeminiServiceError:
    if isinstance(exc, GeminiServiceError):
        return exc
    code = _status_code(exc)
    if code == 400:
        category = "invalid_request"
    elif code == 401:
        category = "authentication"
    elif code == 403:
        category = "authorization"
    elif code == 404:
        category = "model_not_found"
    elif code == 429:
        category = "quota"
    elif code in {500, 502, 503, 504}:
        category = "transient"
    elif isinstance(exc, (TimeoutError, socket.timeout)) or "timeout" in type(exc).__name__.lower():
        category = "timeout"
    elif isinstance(exc, OSError):
        category = "network"
    else:
        category = "unknown"
    return GeminiServiceError(category, str(exc))


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _public_error_message(category: str, _detail: str = "") -> str:
    messages = {
        "authentication": "Gemini authentication failed. Check the API key.",
        "authorization": "This API key is not permitted to use the Gemini API or selected models.",
        "model_not_found": "No generateContent-capable Gemini model is available to this API key.",
        "quota": "Gemini quota or rate limit was reached. Wait and try again.",
        "invalid_request": "Gemini rejected the translation request. Please try again after updating the app.",
        "transient": "Gemini is temporarily unavailable. Limited retries and available-model fallback were attempted.",
        "timeout": "Gemini did not respond before the 20-second request timeout.",
        "network": "Could not reach Gemini. Check your internet, proxy, or SSL settings.",
        "malformed_response": "Gemini returned an unusable translation response.",
        "sdk_missing": "Gemini support is not installed. Install the google-genai dependency and restart the app.",
        "cancelled": "Gemini translation was cancelled.",
        "unknown": "Gemini translation failed unexpectedly. Try the connection diagnostic or try again later.",
    }
    return messages.get(category, messages["unknown"])


def _redact(value: str) -> str:
    return _API_KEY_PATTERN.sub("[redacted API key]", value)


def _require_api_key(api_key: str) -> None:
    if not api_key.strip():
        raise GeminiServiceError("authentication")


def _is_cancelled(should_cancel: Callable[[], bool] | None) -> bool:
    return bool(should_cancel and should_cancel())


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if _is_cancelled(should_cancel):
        raise GeminiCancelled()


def _sleep_with_cancellation(
    seconds: float,
    should_cancel: Callable[[], bool] | None,
    sleep: Callable[[float], None],
) -> None:
    # Short slices make cancellation responsive without a busy wait.
    remaining = seconds
    while remaining > 0:
        _raise_if_cancelled(should_cancel)
        slice_seconds = min(0.1, remaining)
        sleep(slice_seconds)
        remaining -= slice_seconds


def _batches(items: list[tuple[NamePart, str]], size: int) -> Iterable[list[tuple[NamePart, str]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]
