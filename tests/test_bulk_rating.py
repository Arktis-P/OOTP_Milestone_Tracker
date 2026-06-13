"""Bulk rating edit tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.roster.age import calculate_age
from core.roster.bulk_rating import (
    FameLevel,
    PlayerBulkSettings,
    apply_bulk_rules_to_row,
    prospect_boost_eligible,
    should_modify_player,
)
from core.roster.combined import CombinedPlayer, load_combined_roster, save_modified_rosters
from core.roster.columns import validate_fieldnames
from core.roster.ootp_format import load_ootp_roster
from core.roster.row_access import row_get, row_set

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "tests" / "fixtures" / "roster_txt"
LIVE_SAMPLE_DIR = ROOT / "samples" / "roster"


@pytest.fixture
def sample_header() -> list[str]:
    roster = load_ootp_roster(SAMPLE_DIR / "mlb_rosters.txt")
    return roster.fieldnames


def test_calculate_age() -> None:
    assert calculate_age(2000, 6, 15, date(2026, 3, 1)) == 25
    assert calculate_age(2000, 6, 15, date(2026, 6, 15)) == 26


def test_canonical_column_validation(sample_header) -> None:
    warnings = validate_fieldnames(sample_header)
    assert warnings == []


@pytest.mark.parametrize("filename", ["mlb_rosters.txt", "kbo_rosters.txt"])
def test_live_sample_column_validation(filename: str) -> None:
    path = LIVE_SAMPLE_DIR / filename
    if not path.is_file():
        pytest.skip(f"local sample not present: {path}")
    roster = load_ootp_roster(path)
    assert "Velo Pot" in roster.fieldnames
    assert roster.fieldnames.index("Velo Pot") == 156
    warnings = validate_fieldnames(roster.fieldnames)
    assert warnings == []


def test_superstar_prospect_stacking(sample_header) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "Position", "11")
    row_set(row, sample_header, "Velocity", "100")
    row_set(row, sample_header, "Stuff Pot.", "80")
    row_set(row, sample_header, "Move Pot", "70")

    settings = PlayerBulkSettings(
        player_id=1,
        age=24,
        is_prospect=True,
        base_fame=FameLevel.SUPERSTAR,
        prospect_fame=FameLevel.SUPERSTAR,
    )
    updated = apply_bulk_rules_to_row(
        row, sample_header, settings, prospect_boost=True
    )
    # current: 100 * 1.15 * 1.05 + 1 (base superstar) = 121.75 -> 122
    assert row_get(updated, sample_header, "Velocity") == "122"
    # pot: Move 70 * 1.15 * 1.15 = 92.525 -> 93
    assert row_get(updated, sample_header, "Move Pot") == "93"


def test_velo_pot_prospect_plus_one(sample_header) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "Position", "11")
    row_set(row, sample_header, "Velo Pot", "80")

    settings = PlayerBulkSettings(player_id=3, age=22, is_prospect=True, nation="South Korea")
    updated = apply_bulk_rules_to_row(
        row, sample_header, settings, prospect_boost=True, prospect_nation="South Korea"
    )
    # +1 before multipliers (no fame selected)
    assert row_get(updated, sample_header, "Velo Pot") == "81"


def test_fielder_defense_prospect_boost(sample_header) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "Position", "6")
    row_set(row, sample_header, "Infield Range", "100")
    row_set(row, sample_header, "OF Range", "50")

    settings = PlayerBulkSettings(
        player_id=2,
        age=22,
        is_prospect=True,
        nation="South Korea",
    )
    updated = apply_bulk_rules_to_row(
        row, sample_header, settings, prospect_boost=True, prospect_nation="South Korea"
    )
    assert row_get(updated, sample_header, "Infield Range") == "110"
    assert row_get(updated, sample_header, "OF Range") == "50"


def test_prospect_boost_requires_matching_nation(sample_header) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "Position", "11")
    row_set(row, sample_header, "Velo Pot", "80")

    settings = PlayerBulkSettings(
        player_id=4,
        age=22,
        is_prospect=True,
        nation="USA",
    )
    unchanged = apply_bulk_rules_to_row(
        row, sample_header, settings, prospect_boost=True, prospect_nation="South Korea"
    )
    assert unchanged == row

    assert not should_modify_player(
        settings,
        prospect_boost=True,
        prospect_nation="South Korea",
    )
    assert not prospect_boost_eligible(
        settings,
        prospect_boost=True,
        prospect_nation="South Korea",
    )

    kr_settings = PlayerBulkSettings(
        player_id=5,
        age=22,
        is_prospect=True,
        nation="South Korea",
    )
    assert prospect_boost_eligible(
        kr_settings,
        prospect_boost=True,
        prospect_nation="South Korea",
    )


def test_prospect_boost_skipped_when_nation_filter_empty(sample_header) -> None:
    settings = PlayerBulkSettings(
        player_id=6,
        age=22,
        is_prospect=True,
        nation="South Korea",
    )
    assert not should_modify_player(settings, prospect_boost=True, prospect_nation=None)


def test_collect_nations_from_roster(sample_header) -> None:
    row_kr = ["0"] * len(sample_header)
    row_us = ["0"] * len(sample_header)
    row_set(row_kr, sample_header, "Nation", "South Korea")
    row_set(row_us, sample_header, "Nation", "USA")
    row_set(row_kr, sample_header, "id", "1")
    row_set(row_us, sample_header, "id", "2")
    players = [
        CombinedPlayer(1, row_kr, "kbo", 0, sample_header),
        CombinedPlayer(2, row_us, "mlb", 1, sample_header),
    ]
    nations: set[str] = set()
    for player in players:
        nation = row_get(player.row, sample_header, "Nation").strip()
        if nation:
            nations.add(nation)
    assert nations == {"South Korea", "USA"}


def test_combined_dedup(tmp_path: Path, sample_header) -> None:
    mlb = SAMPLE_DIR / "mlb_rosters.txt"
    kbo = tmp_path / "kbo_rosters.txt"
    kbo.write_text(
        (SAMPLE_DIR / "mlb_rosters.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    combined = load_combined_roster(mlb, kbo)
    ids = [player.player_id for player in combined.players]
    assert len(ids) == len(set(ids))


def test_save_mod_preserves_comments(tmp_path: Path) -> None:
    src = SAMPLE_DIR / "mlb_rosters.txt"
    dst = tmp_path / "mlb_rosters.txt"
    dst.write_bytes(src.read_bytes())
    combined = load_combined_roster(dst, None)
    combined.mlb_path = dst
    mlb_out, _ = save_modified_rosters(combined)
    assert mlb_out is not None
    text = mlb_out.read_text(encoding="utf-8")
    assert text.startswith("//")
