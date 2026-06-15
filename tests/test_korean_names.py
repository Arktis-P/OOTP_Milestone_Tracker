"""Korean name mapping tests."""

from __future__ import annotations

from pathlib import Path

from core.roster.korean_names import (
    KoreanNameMapper,
    KoreanNameStore,
    PlayerNameParts,
    format_korean_from_full_name,
    parse_display_name_parts,
    resolve_player_name_parts,
    split_ootp_full_name,
)


def test_format_player_name_korean_order(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nKim,김\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nTaek-yeon,택연\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameStore.load(tmp_path).to_mapper()
    assert mapper.format_player_name("Kim", "Taek-yeon") == "김택연"
    assert mapper.format_player_name("Kim", "Taek-yeon", western_order=True) == "택연 김"


def test_format_player_name_western_order(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nTrout,트라우트\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nMike,마이크\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameStore.load(tmp_path).to_mapper()
    assert mapper.format_player_name("Trout", "Mike", western_order=True) == "마이크 트라우트"


def test_note_pending_and_apply_mapping(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nKim,\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8-sig",
    )
    store = KoreanNameStore.load(tmp_path)
    assert store.note_name("first", "Shohei", source="stats") is True
    assert store.note_name("last", "Kim", source="stats") is True
    assert store.pending_count() == 2

    store.apply_mapping("first", "Shohei", "쇼헤이")
    assert store.first_names["Shohei"] == "쇼헤이"
    assert store.pending_count() == 1

    store.apply_mapping("last", "Kim", "김")
    assert store.pending_count() == 0


def test_merge_seed_preserves_existing_korean(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nKim,김\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8-sig",
    )
    store = KoreanNameStore.load(tmp_path)
    added_last, added_first = store.merge_seed_names({"Kim", "Trout"}, {"Mike"})
    assert added_last == 1
    assert added_first == 1
    assert store.last_names["Kim"] == "김"
    assert store.last_names["Trout"] == ""


def test_split_ootp_full_name() -> None:
    assert split_ootp_full_name("Mike Trout") == ("Mike", "Trout")
    assert split_ootp_full_name("M. Trout") == ("", "")
    assert split_ootp_full_name("") == ("", "")


def test_parse_display_name_parts_roster_style() -> None:
    assert parse_display_name_parts("Trout, Mike") == ("Mike", "Trout")


def test_format_korean_from_full_name(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nTrout,트라우트\nKim,김\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nMike,마이크\nTaek-yeon,택연\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameStore.load(tmp_path).to_mapper()
    assert format_korean_from_full_name("Mike Trout", mapper) == "마이크 트라우트"
    assert format_korean_from_full_name("Taek-yeon Kim", mapper, nation="South Korea") == "김택연"
    assert format_korean_from_full_name("M. Trout", mapper) == ""


def test_uses_western_name_order() -> None:
    assert KoreanNameMapper.uses_western_name_order("South Korea") is False
    assert KoreanNameMapper.uses_western_name_order("USA") is True
    assert KoreanNameMapper.uses_western_name_order("") is True


def test_resolve_player_name_parts_from_roster_when_db_abbreviated() -> None:
    roster = {
        23848: PlayerNameParts("Patrick", "Bailey", "The United States"),
    }
    parts = resolve_player_name_parts(
        full_name="P. Bailey",
        player_id=23848,
        roster_names=roster,
    )
    assert parts.first_name == "Patrick"
    assert parts.last_name == "Bailey"
    assert parts.nation == "The United States"


def test_format_korean_from_abbreviated_db_with_roster(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nBailey,베일리\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nPatrick,패트릭\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameStore.load(tmp_path).to_mapper()
    roster = {23848: PlayerNameParts("Patrick", "Bailey", "The United States")}
    assert (
        format_korean_from_full_name(
            "P. Bailey",
            mapper,
            player_id=23848,
            roster_names=roster,
        )
        == "패트릭 베일리"
    )


def test_abbreviated_name_queues_unmapped_parts_from_roster(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\nAdam,아담\n",
        encoding="utf-8-sig",
    )
    store = KoreanNameStore.load(tmp_path)
    roster = {99: PlayerNameParts("Adam", "Barnes", "The United States")}

    assert (
        format_korean_from_full_name(
            "A. Barnes",
            store.to_mapper(),
            player_id=99,
            roster_names=roster,
        )
        == ""
    )

    added = store.note_from_full_name(
        "A. Barnes",
        source="boxscore",
        player_id=99,
        roster_names=roster,
    )
    assert added == 1
    assert store.pending_count() == 1
    assert store.pending[0].part == "last"
    assert store.pending[0].name == "Barnes"


def test_load_uses_user_data_dir_not_nested_data(monkeypatch, tmp_path: Path) -> None:
    """Frozen builds seed CSVs directly under user data dir, not user_data/data/."""
    user_dir = tmp_path / "userdata"
    user_dir.mkdir()
    (user_dir / "korean_last_names.csv").write_text(
        "last_name,korean\nTrout,트라우트\n",
        encoding="utf-8-sig",
    )
    (user_dir / "korean_first_names.csv").write_text(
        "first_name,korean\nMike,마이크\n",
        encoding="utf-8-sig",
    )
    (user_dir / "korean_names_pending.csv").write_text(
        "part,name,source,first_seen\n",
        encoding="utf-8-sig",
    )

    import core.config.paths as paths
    import core.roster.korean_names as korean_names

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: user_dir)
    monkeypatch.setattr(korean_names, "ensure_user_data_dir", lambda: user_dir)
    paths._USER_DATA_READY = True

    mapper = KoreanNameStore.load().to_mapper()
    assert mapper.format_player_name("Trout", "Mike", western_order=True) == "마이크 트라우트"


def test_partial_mapping_not_shown_when_both_parts_known(tmp_path: Path) -> None:
    (tmp_path / "korean_last_names.csv").write_text(
        "last_name,korean\nTrout,트라우트\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "korean_first_names.csv").write_text(
        "first_name,korean\n",
        encoding="utf-8-sig",
    )
    mapper = KoreanNameStore.load(tmp_path).to_mapper()
    assert mapper.format_player_name("Trout", "Mike", western_order=True) == ""
