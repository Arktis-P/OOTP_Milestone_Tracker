"""Offline tests for the Gemini recovery path.

No test in this module calls the live Gemini API.  A live connection check is
available only through the explicit ``diagnose_gemini`` application action.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket

import pytest

from core.roster.gemini_korean import (
    GeminiServiceError,
    diagnose_gemini,
    translate_names_via_gemini,
    translate_names_with_gemini,
)


class ApiError(Exception):
    def __init__(self, code: int, message: str = "service error") -> None:
        self.code = code
        super().__init__(message)


@dataclass
class Model:
    name: str
    supported_actions: tuple[str, ...] = ("generateContent",)


@dataclass
class Response:
    text: str


class Models:
    def __init__(self, models: list[Model], responses) -> None:
        self._models = models
        self._responses = responses
        self.calls: list[str] = []

    def list(self):
        return self._models

    def generate_content(self, *, model: str, contents: str):
        self.calls.append(model)
        value = self._responses(model, contents, len(self.calls)) if callable(self._responses) else self._responses
        if isinstance(value, Exception):
            raise value
        return value


class Client:
    def __init__(self, models: Models) -> None:
        self.models = models


def factory(client: Client):
    return lambda _key, _options: client


def csv_response(_model: str, contents: str, _call: int) -> Response:
    rows = []
    for line in contents.split("Input CSV:\npart,roman\n", 1)[1].splitlines():
        if line:
            part, roman = line.split(",", 1)
            rows.append(f"{part},{roman},번역{roman}")
    return Response("part,roman,korean\n" + "\n".join(rows))


def test_discovers_supported_model_and_translates() -> None:
    models = Models(
        [Model("models/not-for-content", ("embedContent",)), Model("models/gemini-3.5-flash")],
        csv_response,
    )
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", [("last", "Kim")], client_factory=factory(Client(models))
    )

    assert result.translations == {("last", "Kim"): "번역Kim"}
    assert result.selected_models == ("gemini-3.5-flash",)
    assert models.calls == ["gemini-3.5-flash"]


@pytest.mark.parametrize("status,category", [(401, "authentication"), (403, "authorization")])
def test_authentication_and_authorization_are_classified(status: int, category: str) -> None:
    class FailingModels(Models):
        def list(self):
            raise ApiError(status)

    with pytest.raises(GeminiServiceError) as error:
        diagnose_gemini("AIza-test-key-not-real", client_factory=factory(Client(FailingModels([], csv_response))))
    assert error.value.category == category


def test_invalid_request_is_not_retried_or_hidden_by_fallback() -> None:
    models = Models([Model("gemini-3.5-flash"), Model("gemini-3.1-flash-lite")], ApiError(400))
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", [("last", "Kim")], client_factory=factory(Client(models))
    )
    assert result.failures[0].error.category == "invalid_request"
    assert models.calls == ["gemini-3.5-flash"]


def test_network_error_is_classified_and_retried_within_bound() -> None:
    models = Models([Model("gemini-3.5-flash")], socket.gaierror("DNS unavailable"))
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", [("last", "Kim")], client_factory=factory(Client(models)), sleep=lambda _: None
    )
    assert result.failures[0].error.category == "network"
    assert len(models.calls) == 2


def test_missing_model_falls_back_to_next_discovered_model() -> None:
    def responses(model: str, contents: str, _call: int):
        return ApiError(404) if model == "gemini-3.5-flash" else csv_response(model, contents, 1)

    models = Models([Model("gemini-3.5-flash"), Model("gemini-3.1-flash-lite")], responses)
    translated = translate_names_via_gemini(
        "AIza-test-key-not-real", [("first", "Mike")], client_factory=factory(Client(models))
    )
    assert translated[("first", "Mike")] == "번역Mike"
    assert models.calls == ["gemini-3.5-flash", "gemini-3.1-flash-lite"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_limited_retry_recovers_transient_and_quota_errors(status: int) -> None:
    def responses(model: str, contents: str, call: int):
        return ApiError(status) if call == 1 else csv_response(model, contents, call)

    models = Models([Model("gemini-3.5-flash")], responses)
    result = translate_names_with_gemini(
        "AIza-test-key-not-real",
        [("last", "Park")],
        client_factory=factory(Client(models)),
        sleep=lambda _seconds: None,
    )
    assert result.translations[("last", "Park")] == "번역Park"
    assert models.calls == ["gemini-3.5-flash", "gemini-3.5-flash"]


def test_timeout_is_classified_without_unbounded_retry() -> None:
    models = Models([Model("gemini-3.5-flash")], TimeoutError("too slow"))
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", [("last", "Lee")], client_factory=factory(Client(models)), sleep=lambda _: None
    )
    assert result.failures[0].error.category == "timeout"
    assert len(models.calls) == 2


def test_malformed_response_is_reported() -> None:
    models = Models([Model("gemini-3.5-flash")], Response("not a CSV response"))
    with pytest.raises(GeminiServiceError) as error:
        translate_names_via_gemini(
            "AIza-test-key-not-real", [("last", "Choi")], client_factory=factory(Client(models))
        )
    assert error.value.category == "malformed_response"


def test_partial_csv_response_keeps_valid_rows_without_inventing_mappings() -> None:
    models = Models(
        [Model("gemini-3.5-flash")],
        Response("part,roman,korean\nlast,Kim,김\nnot-a-csv-row\nfirst,,빈값"),
    )
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", [("last", "Kim"), ("first", "Min")], client_factory=factory(Client(models))
    )
    assert result.translations == {("last", "Kim"): "김"}


def test_partial_results_are_preserved_when_a_later_batch_fails() -> None:
    def responses(_model: str, contents: str, _call: int):
        return ApiError(503) if "Name40" in contents else csv_response(_model, contents, _call)

    items = [("first", f"Name{index}") for index in range(41)]
    result = translate_names_with_gemini(
        "AIza-test-key-not-real", items, client_factory=factory(Client(Models([Model("gemini-3.5-flash")], responses))), sleep=lambda _: None
    )
    assert len(result.translations) == 40
    assert result.is_partial
    assert result.failures[0].error.category == "transient"


def test_cancellation_preserves_completed_batches() -> None:
    calls = 0

    def responses(model: str, contents: str, call: int):
        nonlocal calls
        calls += 1
        return csv_response(model, contents, call)

    items = [("first", f"Name{index}") for index in range(41)]
    result = translate_names_with_gemini(
        "AIza-test-key-not-real",
        items,
        client_factory=factory(Client(Models([Model("gemini-3.5-flash")], responses))),
        should_cancel=lambda: calls >= 1,
    )
    assert result.cancelled
    assert len(result.translations) == 40


def test_all_models_failing_returns_a_safe_failure_and_redacts_key() -> None:
    leaked_key = "AIzaVeryLongButFakeKeyValue_123456789"
    models = Models(
        [Model("gemini-3.5-flash"), Model("gemini-3.1-flash-lite")],
        ApiError(503, leaked_key),
    )
    result = translate_names_with_gemini(
        leaked_key, [("last", "Ryu")], client_factory=factory(Client(models)), sleep=lambda _: None
    )
    assert result.failures[0].error.category == "transient"
    assert leaked_key not in str(result.failures[0].error)
    # Two bounded attempts per model, then one failed batch result.
    assert len(models.calls) == 4
