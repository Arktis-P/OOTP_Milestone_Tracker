"""Gemini API integration for Korean name translation."""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
from typing import Callable, Literal

NamePart = Literal["last", "first"]

# Fallback order: if the primary model is overloaded (503) or rate-limited
# (429), retry against progressively lighter/older models before giving up.
_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")
_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS_PER_MODEL = 3
_RETRY_BACKOFF_S = (2, 5, 10)

_PROMPT_HEADER = (
    "다음 선수들은 메이저리그에서 뛰었거나 뛴 야구 선수의 성(last) 또는 이름(first)입니다.\n"
    "이를 참고해서 가장 널리 쓰인 한글 표기로 변환해주세요.\n"
    "반드시 아래 CSV 형식으로만 응답하세요 (헤더 없이, 코드 블록 없이):\n"
    "part,roman,korean\n\n"
    "입력:\n"
)


def translate_names_via_gemini(
    api_key: str,
    items: list[tuple[NamePart, str]],
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[tuple[NamePart, str], str]:
    """Return {(part, roman): korean} from the Gemini API. Raises on error.

    Retries transient errors (503 "high demand", 429, 5xx) with backoff, and
    falls back to lighter models if the primary one stays unavailable.
    `on_status` is called with a short progress message before each attempt
    so callers can surface retry/fallback progress in the UI.
    """
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    if not items:
        return {}

    lines = "\n".join(f"{part},{name}" for part, name in items)
    prompt = _PROMPT_HEADER + lines
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")

    last_error: Exception | None = None
    for model_index, model in enumerate(_MODELS):
        url = _API_URL_TEMPLATE.format(model=model) + f"?key={api_key}"
        for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
            if on_status:
                if attempt == 0:
                    on_status(f"Gemini 요청 중 ({model})...")
                else:
                    on_status(f"Gemini 재시도 중 ({model}, {attempt + 1}/{_MAX_ATTEMPTS_PER_MODEL})...")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = json.loads(resp.read())
                return _parse_gemini_response(raw)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Gemini API 오류 {exc.code}: {body}")
                if exc.code not in _RETRYABLE_STATUS:
                    raise last_error from exc
                if attempt < _MAX_ATTEMPTS_PER_MODEL - 1:
                    time.sleep(_RETRY_BACKOFF_S[attempt])
            except OSError as exc:
                last_error = RuntimeError(f"네트워크 오류: {exc}")
                if attempt < _MAX_ATTEMPTS_PER_MODEL - 1:
                    time.sleep(_RETRY_BACKOFF_S[attempt])
        # Exhausted retries for this model; try the next fallback model.

    assert last_error is not None
    raise last_error


def _parse_gemini_response(raw: dict) -> dict[tuple[NamePart, str], str]:
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Gemini 응답 파싱 실패: {raw}") from exc
    return _parse_csv_response(text)


def _parse_csv_response(text: str) -> dict[tuple[NamePart, str], str]:
    result: dict[tuple[NamePart, str], str] = {}
    lines = text.strip().splitlines()
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or not stripped:
            continue
        clean_lines.append(stripped)

    reader = csv.reader(io.StringIO("\n".join(clean_lines)))
    for row in reader:
        if len(row) < 3:
            continue
        part = row[0].strip().lower()
        roman = row[1].strip()
        korean = row[2].strip()
        if part not in ("last", "first") or not roman or not korean:
            continue
        result[(part, roman)] = korean  # type: ignore[index]
    return result
