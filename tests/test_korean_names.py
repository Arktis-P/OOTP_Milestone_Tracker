"""Korean name mapping tests."""

from __future__ import annotations

from pathlib import Path

from core.roster.korean_names import KoreanNameMapper


def test_format_player_name_combines_parts(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nKim,김\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nTaek-yeon,택연\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameMapper.load(tmp_path)
    assert mapper.format_player_name("Kim", "Taek-yeon") == "김택연"


def test_format_player_name_partial_mapping(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nLee,이\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameMapper.load(tmp_path)
    assert mapper.format_player_name("Lee", "Unknown") == "이"
    assert mapper.format_player_name("Unknown", "Min-ho") == ""


def test_missing_csv_returns_empty_mapper(tmp_path: Path) -> None:
    mapper = KoreanNameMapper.load(tmp_path)
    assert mapper.format_player_name("Kim", "Min-ho") == ""
