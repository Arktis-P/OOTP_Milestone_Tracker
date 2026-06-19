"""MLB/KBO-style roman name → Hangul fallback when not in curated reference."""

from __future__ import annotations

import re
from typing import Literal

NamePart = Literal["last", "first"]

_MULTI_PHONEMES: tuple[tuple[str, str], ...] = (
    ("ough", "오"),
    ("eigh", "에이"),
    ("augh", "오"),
    ("sch", "슈"),
    ("tion", "션"),
    ("cia", "샤"),
    ("cio", "시오"),
    ("quez", "케스"),
    ("sh", "시"),
    ("ch", "치"),
    ("th", "스"),
    ("ph", "프"),
    ("gh", ""),
    ("ck", "크"),
    ("qu", "쿼"),
    ("wh", "웨"),
    ("wr", "르"),
    ("kn", "느"),
    ("ng", "응"),
    ("tz", "츠"),
    ("ts", "츠"),
    ("zh", "즈"),
    ("ae", "애"),
    ("ai", "에이"),
    ("ay", "에이"),
    ("ey", "이"),
    ("ie", "이"),
    ("ei", "아이"),
    ("eu", "유"),
    ("au", "오"),
    ("aw", "오"),
    ("ow", "오"),
    ("oo", "우"),
    ("ou", "우"),
    ("oa", "오"),
    ("ea", "이"),
    ("ee", "이"),
    ("ia", "이아"),
    ("io", "이오"),
    ("ei", "에이"),
    ("ez", "에즈"),
    ("es", "에스"),
    ("as", "아스"),
    ("os", "오스"),
    ("is", "이스"),
    ("us", "어스"),
    ("son", "슨"),
    ("ski", "스키"),
    ("sky", "스키"),
    ("man", "맨"),
    ("ner", "너"),
    ("ley", "리"),
    ("ton", "턴"),
    ("don", "던"),
    ("son", "슨"),
    ("man", "먼"),
    ("ez", "에즈"),
)

_CONSONANT_VOWEL: tuple[tuple[str, str, str], ...] = (
    ("b", "a", "바"),
    ("b", "e", "베"),
    ("b", "i", "비"),
    ("b", "o", "보"),
    ("b", "u", "부"),
    ("b", "y", "비"),
    ("c", "a", "카"),
    ("c", "e", "체"),
    ("c", "i", "시"),
    ("c", "o", "코"),
    ("c", "u", "커"),
    ("c", "y", "시"),
    ("d", "a", "다"),
    ("d", "e", "데"),
    ("d", "i", "디"),
    ("d", "o", "도"),
    ("d", "u", "두"),
    ("d", "y", "디"),
    ("f", "a", "파"),
    ("f", "e", "페"),
    ("f", "i", "피"),
    ("f", "o", "포"),
    ("f", "u", "푸"),
    ("g", "a", "가"),
    ("g", "e", "게"),
    ("g", "i", "지"),
    ("g", "o", "고"),
    ("g", "u", "구"),
    ("h", "a", "하"),
    ("h", "e", "헤"),
    ("h", "i", "히"),
    ("h", "o", "호"),
    ("h", "u", "후"),
    ("j", "a", "자"),
    ("j", "e", "제"),
    ("j", "i", "지"),
    ("j", "o", "조"),
    ("j", "u", "주"),
    ("k", "a", "카"),
    ("k", "e", "케"),
    ("k", "i", "키"),
    ("k", "o", "코"),
    ("k", "u", "쿠"),
    ("l", "a", "라"),
    ("l", "e", "레"),
    ("l", "i", "리"),
    ("l", "o", "로"),
    ("l", "u", "루"),
    ("l", "y", "리"),
    ("m", "a", "마"),
    ("m", "e", "메"),
    ("m", "i", "미"),
    ("m", "o", "모"),
    ("m", "u", "무"),
    ("n", "a", "나"),
    ("n", "e", "네"),
    ("n", "i", "니"),
    ("n", "o", "노"),
    ("n", "u", "누"),
    ("p", "a", "파"),
    ("p", "e", "페"),
    ("p", "i", "피"),
    ("p", "o", "포"),
    ("p", "u", "푸"),
    ("r", "a", "라"),
    ("r", "e", "레"),
    ("r", "i", "리"),
    ("r", "o", "로"),
    ("r", "u", "루"),
    ("r", "y", "리"),
    ("s", "a", "사"),
    ("s", "e", "세"),
    ("s", "i", "시"),
    ("s", "o", "소"),
    ("s", "u", "수"),
    ("s", "y", "시"),
    ("t", "a", "타"),
    ("t", "e", "테"),
    ("t", "i", "티"),
    ("t", "o", "토"),
    ("t", "u", "투"),
    ("t", "y", "티"),
    ("v", "a", "바"),
    ("v", "e", "베"),
    ("v", "i", "비"),
    ("v", "o", "보"),
    ("v", "u", "부"),
    ("w", "a", "와"),
    ("w", "e", "웨"),
    ("w", "i", "위"),
    ("w", "o", "워"),
    ("w", "u", "우"),
    ("z", "a", "자"),
    ("z", "e", "제"),
    ("z", "i", "지"),
    ("z", "o", "조"),
    ("z", "u", "주"),
)

_VOWEL_ONLY: dict[str, str] = {
    "a": "아",
    "e": "에",
    "i": "이",
    "o": "오",
    "u": "우",
    "y": "이",
}

_CONSONANT_END: dict[str, str] = {
    "b": "브",
    "c": "크",
    "d": "드",
    "f": "프",
    "g": "그",
    "h": "흐",
    "j": "지",
    "k": "크",
    "l": "을",
    "m": "",
    "n": "",
    "p": "프",
    "r": "르",
    "s": "스",
    "t": "트",
    "v": "브",
    "w": "우",
    "x": "ks",
    "z": "즈",
}


def mlb_phonetic_hangul(
    roman: str,
    part: NamePart,
    *,
    _skip_japanese: bool = False,
) -> str:
    """Best-effort MLB broadcast-style transliteration for unknown names."""
    text = roman.strip()
    if not text:
        return ""

    if not _skip_japanese and part == "first" and _looks_japanese_roman(text):
        return _japanese_roman_to_hangul(text)

    lower = text.lower()
    index = 0
    pieces: list[str] = []

    while index < len(lower):
        matched = False
        for pattern, hangul in _MULTI_PHONEMES:
            if lower.startswith(pattern, index):
                if hangul:
                    pieces.append(hangul)
                index += len(pattern)
                matched = True
                break
        if matched:
            continue

        char = lower[index]
        if char in "aeiouy":
            if pieces and pieces[-1][-1] in "ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ":
                pieces.append(_VOWEL_ONLY.get(char, ""))
            else:
                pieces.append(_VOWEL_ONLY.get(char, ""))
            index += 1
            continue

        if index + 1 < len(lower) and lower[index + 1] in "aeiouy":
            consonant = char
            vowel = lower[index + 1]
            syllable = _consonant_vowel(consonant, vowel)
            if syllable:
                pieces.append(syllable)
                index += 2
                continue

        if char in _CONSONANT_END:
            pieces.append(_CONSONANT_END[char])
        index += 1

    result = "".join(pieces)
    return _postprocess(result, part)


def _consonant_vowel(consonant: str, vowel: str) -> str:
    for c, v, hangul in _CONSONANT_VOWEL:
        if c == consonant and v == vowel:
            return hangul
    return ""


def _looks_japanese_roman(text: str) -> bool:
    lower = text.casefold()
    if lower in {"shohei", "yoshinobu", "kenta", "kazuma", "yuki", "sota", "ryu", "ryo"}:
        return True
    return bool(re.fullmatch(r"[a-z\-]{2,20}", lower) and lower.endswith(("i", "o", "u", "e")))


def _japanese_roman_to_hangul(text: str) -> str:
    if "-" in text:
        return "".join(_japanese_roman_to_hangul(segment) for segment in text.split("-") if segment.strip())
    lower = text.casefold()
    _KNOWN = {
        "shohei": "쇼헤이",
        "yoshinobu": "요시노부",
        "yuki": "유키",
        "sota": "소타",
        "ryu": "류",
        "ryo": "료",
        "kenta": "켄타",
    }
    if lower in _KNOWN:
        return _KNOWN[lower]
    return mlb_phonetic_hangul(text, "first", _skip_japanese=True)


def _postprocess(text: str, part: NamePart) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if part == "last":
        cleaned = cleaned.replace(" ", "")
    return cleaned
