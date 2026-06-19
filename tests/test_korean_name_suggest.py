"""Tests for automatic Korean name suggestions."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.roster.korean_name_reference import clear_reference_cache, load_merged_reference
from core.roster.korean_name_suggest import suggest_korean_name
from core.roster.mlb_name_phonetic import mlb_phonetic_hangul

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _reset_reference_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_suggest_skips_initials() -> None:
    assert suggest_korean_name("first", "A.J.") == ""
    assert suggest_korean_name("first", "AJ") == ""


def test_suggest_common_korean_surname() -> None:
    assert suggest_korean_name("last", "Kim") == "김"
    assert suggest_korean_name("last", "Ahn") == "안"


def test_phonetic_fallback_does_not_recursion_error_on_japanese_heuristic() -> None:
    assert mlb_phonetic_hangul("Mike", "first")
    assert mlb_phonetic_hangul("Kazuma", "first")
    assert suggest_korean_name("first", "Kazuma")


def test_suggest_from_bundled_mlb_reference() -> None:
    assert suggest_korean_name("last", "Trout") == "트라웃"
    assert suggest_korean_name("last", "Schwarber") == "슈와버"
    assert suggest_korean_name("last", "Acuna Jr.") == "아쿠냐 주니어"
    assert suggest_korean_name("first", "Ah-seop") == "아섭"
    assert suggest_korean_name("first", "Shohei") == "쇼헤이"
    assert suggest_korean_name("last", "Ohtani") == "오타니"


def test_suggest_hyphenated_first_name() -> None:
    result = suggest_korean_name("first", "Hyun-min")
    assert result == "현민"


def test_suggest_matches_curated_reference(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "korean_last_names.csv").write_text(
        "last_name,korean\nCustom,커스텀\n",
        encoding="utf-8-sig",
    )
    (data_dir / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8-sig",
    )
    (data_dir / "korean_names_pending.csv").write_text(
        "part,name,source,first_seen\n",
        encoding="utf-8-sig",
    )

    assert suggest_korean_name("last", "Custom", data_dir=str(data_dir)) == "커스텀"
    assert suggest_korean_name("last", "Trout", data_dir=str(data_dir)) == "트라웃"


def test_reference_covers_most_bundled_last_names() -> None:
    last_names, first_names = load_merged_reference(ROOT / "data")
    missed: list[tuple[str, str, str]] = []
    for name, expected in last_names.items():
        got = suggest_korean_name("last", name, data_dir=str(ROOT / "data"))
        if got != expected:
            missed.append((name, expected, got))
    ratio = 1 - (len(missed) / max(len(last_names), 1))
    assert ratio >= 0.98, f"last-name coverage {ratio:.1%}, sample: {missed[:5]}"

    missed_first: list[tuple[str, str, str]] = []
    for name, expected in first_names.items():
        got = suggest_korean_name("first", name, data_dir=str(ROOT / "data"))
        if got != expected:
            missed_first.append((name, expected, got))
    ratio_first = 1 - (len(missed_first) / max(len(first_names), 1))
    assert ratio_first >= 0.98, f"first-name coverage {ratio_first:.1%}, sample: {missed_first[:5]}"
