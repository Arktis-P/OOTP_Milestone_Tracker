"""OOTP roster position codes and filter groups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

POSITION_LABELS: dict[int, str] = {
    2: "C",
    3: "1B",
    4: "2B",
    5: "3B",
    6: "SS",
    7: "LF",
    8: "CF",
    9: "RF",
    10: "DH",
    11: "SP",
    12: "RP",
    13: "CP",
}

POSITION_GROUP_OPTIONS: list[tuple[str, str | None]] = [
    ("전체", None),
    ("C (2)", "c"),
    ("IF (3-6)", "if"),
    ("OF (7-9)", "of"),
    ("DH (10)", "dh"),
    ("SP (11)", "sp"),
    ("RP (12)", "rp"),
    ("CP (13)", "cp"),
]

_POSITION_GROUPS: dict[str, FrozenSet[int]] = {
    "c": frozenset({2}),
    "if": frozenset({3, 4, 5, 6}),
    "of": frozenset({7, 8, 9}),
    "dh": frozenset({10}),
    "sp": frozenset({11}),
    "rp": frozenset({12}),
    "cp": frozenset({13}),
}


@dataclass(frozen=True)
class PositionGroup:
    key: str | None
    codes: FrozenSet[int] | None

    @property
    def label(self) -> str:
        for text, value in POSITION_GROUP_OPTIONS:
            if value == self.key:
                return text
        return "전체"


def parse_position_code(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def position_label(raw: str) -> str:
    code = parse_position_code(raw)
    if code is None:
        return raw
    return POSITION_LABELS.get(code, str(code))


def position_group_codes(group_key: str | None) -> FrozenSet[int] | None:
    if not group_key:
        return None
    return _POSITION_GROUPS.get(group_key)


def matches_position_group(raw: str, group_key: str | None) -> bool:
    codes = position_group_codes(group_key)
    if codes is None:
        return True
    code = parse_position_code(raw)
    return code in codes if code is not None else False
