"""Suggested Korean spellings for pending roman name parts."""

from __future__ import annotations

import difflib
import re
from typing import Literal

from core.roster.korean_name_reference import get_reference, lookup_reference_ci
from core.roster.mlb_name_phonetic import mlb_phonetic_hangul

NamePart = Literal["last", "first"]

_INITIALS_ONLY = re.compile(r"^[A-Z](?:\.[A-Z])+\.?$|^[A-Z]{1,3}$")
_SUFFIX_RE = re.compile(r"\s+(Jr\.?|Sr\.?|III|II|IV)$", re.I)

_COMMON_KOREAN_SURNAMES: dict[str, str] = {
    "Ahn": "안",
    "Bae": "배",
    "Bang": "방",
    "Cha": "차",
    "Chae": "채",
    "Choi": "최",
    "Cho": "조",
    "Go": "고",
    "Gwon": "권",
    "Han": "한",
    "Heo": "허",
    "Hong": "홍",
    "Hwang": "황",
    "Im": "임",
    "Jang": "장",
    "Jeong": "정",
    "Jeon": "전",
    "Jo": "조",
    "Jung": "정",
    "Kang": "강",
    "Kim": "김",
    "Ko": "고",
    "Kwon": "권",
    "Lee": "이",
    "Lim": "임",
    "Moon": "문",
    "Na": "나",
    "Nam": "남",
    "Oh": "오",
    "Park": "박",
    "Ryu": "류",
    "Seo": "서",
    "Shin": "신",
    "Sim": "심",
    "Son": "손",
    "Song": "송",
    "Yang": "양",
    "Yeo": "여",
    "Yoon": "윤",
    "Yoo": "유",
    "Yu": "유",
}

_SUFFIX_KOREAN = {
    "jr": "주니어",
    "sr": "시니어",
    "ii": "2세",
    "iii": "3세",
    "iv": "4세",
}

_ROMAN_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Mc", "맥"),
    ("Mac", "맥"),
    ("O'", "오"),
    ("St. ", "세인트 "),
    ("Saint ", "세인트 "),
    ("Van ", "반 "),
    ("De ", "드"),
    ("De", "드"),
    ("La ", "라"),
    ("La", "라"),
    ("Le ", "르"),
    ("Del ", "델 "),
)

_FUZZY_CUTOFF = 0.93
_NEAREST_CUTOFF = 0.86


def suggest_korean_name(
    part: NamePart,
    roman: str,
    *,
    data_dir: str | None = None,
) -> str:
    """Return a recommended Hangul spelling for a pending roman name part."""
    name = roman.strip()
    if not name or _is_initials_only(name):
        return ""

    if part == "last" and name in _COMMON_KOREAN_SURNAMES:
        return _COMMON_KOREAN_SURNAMES[name]

    if hit := lookup_reference_ci(part, name, data_dir=data_dir):
        return hit

    base, suffix = _split_suffix(name)
    if suffix:
        inner = _suggest_core(part, base, data_dir=data_dir)
        if inner:
            return f"{inner} {suffix}".strip()
        return ""

    return _suggest_core(part, base, data_dir=data_dir)


def _suggest_core(part: NamePart, name: str, *, data_dir: str | None) -> str:
    if hit := lookup_reference_ci(part, name, data_dir=data_dir):
        return hit

    for prefix, hangul_prefix in _ROMAN_PREFIXES:
        if not name.startswith(prefix) or len(name) <= len(prefix):
            continue
        rest = name[len(prefix) :]
        rest_hit = _lookup_simple(part, rest, data_dir=data_dir)
        if rest_hit:
            if hangul_prefix.endswith(" "):
                return f"{hangul_prefix.strip()} {rest_hit}".strip()
            return f"{hangul_prefix}{rest_hit}"

    if "-" in name:
        if hit := lookup_reference_ci(part, name, data_dir=data_dir):
            return hit
        segments: list[str] = []
        for segment in name.split("-"):
            piece = segment.strip()
            if not piece:
                continue
            segment_hit = _lookup_simple(part, piece, data_dir=data_dir)
            if not segment_hit:
                return ""
            segments.append(segment_hit)
        return "".join(segments)

    if fuzzy := _fuzzy_reference(part, name, data_dir=data_dir):
        return fuzzy

    if nearest := _nearest_reference(part, name, data_dir=data_dir):
        return nearest

    return mlb_phonetic_hangul(name, part)


def _lookup_simple(part: NamePart, name: str, *, data_dir: str | None) -> str:
    if hit := lookup_reference_ci(part, name, data_dir=data_dir):
        return hit
    if fuzzy := _fuzzy_reference(part, name, data_dir=data_dir):
        return fuzzy
    if nearest := _nearest_reference(part, name, data_dir=data_dir):
        return nearest
    return mlb_phonetic_hangul(name, part)


def _fuzzy_reference(part: NamePart, name: str, *, data_dir: str | None) -> str:
    table = get_reference(data_dir)[0 if part == "last" else 1]
    if not table:
        return ""
    matches = difflib.get_close_matches(name, list(table.keys()), n=1, cutoff=_FUZZY_CUTOFF)
    if matches:
        return table[matches[0]]
    return ""


def _nearest_reference(part: NamePart, name: str, *, data_dir: str | None) -> str:
    table = get_reference(data_dir)[0 if part == "last" else 1]
    if not table:
        return ""

    best_key = ""
    best_ratio = 0.0
    needle = name.casefold()
    for key in table:
        ratio = difflib.SequenceMatcher(None, needle, key.casefold()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = key
    if best_key and best_ratio >= _NEAREST_CUTOFF:
        return table[best_key]
    return ""


def _is_initials_only(name: str) -> bool:
    return bool(_INITIALS_ONLY.fullmatch(name.strip()))


def _split_suffix(name: str) -> tuple[str, str]:
    match = _SUFFIX_RE.search(name)
    if not match:
        return name.strip(), ""
    token = match.group(1).lower().rstrip(".")
    base = name[: match.start()].strip()
    suffix = _SUFFIX_KOREAN.get(token, match.group(1).strip())
    return base, suffix
