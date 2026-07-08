"""Gemini API integration for Korean name translation."""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from typing import Literal

NamePart = Literal["last", "first"]

_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

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
) -> dict[tuple[NamePart, str], str]:
    """Return {(part, roman): korean} from the Gemini API. Raises on error."""
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    if not items:
        return {}

    lines = "\n".join(f"{part},{name}" for part, name in items)
    prompt = _PROMPT_HEADER + lines

    payload = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}]}
    ).encode("utf-8")

    url = f"{_API_URL}?key={api_key}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API 오류 {exc.code}: {body}") from exc
    except OSError as exc:
        raise RuntimeError(f"네트워크 오류: {exc}") from exc

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
