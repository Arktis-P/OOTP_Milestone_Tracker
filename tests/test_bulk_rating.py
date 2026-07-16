"""Bulk rating edit tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.roster.age import calculate_age
from core.roster.bulk_rating import (
    FameLevel,
    PlayerBulkSettings,
    apply_bulk_rating_plan,
    apply_bulk_rules_to_row,
    build_bulk_rating_plan,
    prospect_boost_eligible,
    should_modify_player,
)
from core.roster.combined import (
    CombinedPlayer,
    load_combined_roster,
    save_modified_rosters,
    save_modified_rosters_safely,
    sync_player_rows_to_sources,
)
import core.roster.combined as combined_module
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
    assert combined.players
    assert all(player.duplicate_player_id for player in combined.players)


def test_loaded_duplicate_id_is_excluded_from_rating_plan(
    tmp_path: Path,
) -> None:
    mlb = tmp_path / "mlb_rosters.txt"
    kbo = tmp_path / "kbo_rosters.txt"
    source = SAMPLE_DIR / "mlb_rosters.txt"
    mlb.write_bytes(source.read_bytes())
    kbo.write_bytes(source.read_bytes())
    combined = load_combined_roster(mlb, kbo)
    player = combined.players[0]
    settings = {
        player.player_id: PlayerBulkSettings(
            player.player_id, 30, False, base_fame=FameLevel.REGIONAL
        )
    }

    plan = build_bulk_rating_plan(
        combined.players,
        [player.player_id],
        settings,
        prospect_boost=False,
    )

    assert plan.changes == ()
    assert plan.skipped == (
        (player.player_id, "duplicate player id in source rosters"),
    )


def test_sync_does_not_propagate_canonical_row_to_duplicate_source(
    tmp_path: Path,
) -> None:
    mlb = tmp_path / "mlb_rosters.txt"
    kbo = tmp_path / "kbo_rosters.txt"
    source = SAMPLE_DIR / "mlb_rosters.txt"
    mlb.write_bytes(source.read_bytes())
    kbo.write_bytes(source.read_bytes())
    combined = load_combined_roster(mlb, kbo)
    player = combined.players[0]
    other = combined.kbo if player.source == "mlb" else combined.mlb
    assert other is not None
    other_index = next(
        index
        for index, row in enumerate(other.rows)
        if row_get(row, other.fieldnames, "id") == str(player.player_id)
    )
    other_before = list(other.rows[other_index])
    row_set(player.row, player.fieldnames, "LastName", "PreviewOnly")

    sync_player_rows_to_sources(combined)

    assert other.rows[other_index] == other_before


def test_combined_player_reads_its_own_field_order() -> None:
    player = CombinedPlayer(
        77,
        ["KBO", "77", "Kim"],
        "kbo",
        0,
        ["Team Name", "id", "LastName"],
    )

    assert player.value("id") == "77"
    assert player.value("Team Name") == "KBO"
    assert player.value("LastName") == "Kim"


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


def test_bulk_plan_is_noop_without_selected_rule(sample_header) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "id", "101")
    player = CombinedPlayer(101, row, "mlb", 0, sample_header)
    settings = {101: PlayerBulkSettings(101, 24, True, nation="South Korea")}

    plan = build_bulk_rating_plan(
        [player],
        [101],
        settings,
        prospect_boost=False,
    )

    assert plan.changed_player_count == 0
    assert plan.changed_cell_count == 0
    assert plan.unchanged == ((101, "no rating rule selected"),)


def test_bulk_plan_and_apply_are_limited_to_explicit_scope(sample_header) -> None:
    first = ["0"] * len(sample_header)
    second = ["0"] * len(sample_header)
    for player_id, row in ((201, first), (202, second)):
        row_set(row, sample_header, "id", str(player_id))
        row_set(row, sample_header, "Position", "1")
        row_set(row, sample_header, "Contact vL", "100")
    players = [
        CombinedPlayer(201, first, "mlb", 0, sample_header),
        CombinedPlayer(202, second, "mlb", 1, sample_header),
    ]
    settings = {
        player_id: PlayerBulkSettings(
            player_id, 30, False, base_fame=FameLevel.REGIONAL
        )
        for player_id in (201, 202)
    }

    plan = build_bulk_rating_plan(
        players,
        [201],
        settings,
        prospect_boost=False,
    )
    assert plan.changed_player_count == 1
    assert plan.changes[0].player_id == 201
    assert any(
        cell.header == "Contact vL" and cell.before == "100" and cell.after == "105"
        for cell in plan.changes[0].cells
    )

    apply_bulk_rating_plan(players, plan)
    assert row_get(players[0].row, sample_header, "Contact vL") == "105"
    assert row_get(players[1].row, sample_header, "Contact vL") == "100"


def test_bulk_plan_skips_duplicate_player_ids(sample_header) -> None:
    row = ["0"] * len(sample_header)
    settings = {
        301: PlayerBulkSettings(301, 30, False, base_fame=FameLevel.REGIONAL)
    }
    players = [
        CombinedPlayer(301, row, "mlb", 0, sample_header),
        CombinedPlayer(301, list(row), "kbo", 0, sample_header),
    ]

    plan = build_bulk_rating_plan(
        players, [301], settings, prospect_boost=False
    )

    assert plan.changes == ()
    assert plan.skipped == ((301, "duplicate player id"),)


def test_safe_save_creates_backup_for_existing_mod(tmp_path: Path) -> None:
    src = SAMPLE_DIR / "mlb_rosters.txt"
    dst = tmp_path / "mlb_rosters.txt"
    dst.write_bytes(src.read_bytes())
    old_output = tmp_path / "mod_mlb_rosters.txt"
    old_output.write_text("old output", encoding="utf-8")
    combined = load_combined_roster(dst, None)

    result = save_modified_rosters_safely(combined)

    assert result.mlb_output == old_output
    assert old_output.read_text(encoding="utf-8").startswith("//")
    assert len(result.backups) == 1
    assert result.backups[0].read_text(encoding="utf-8") == "old output"


def test_safe_save_rolls_back_first_output_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = SAMPLE_DIR / "mlb_rosters.txt"
    mlb = tmp_path / "mlb_rosters.txt"
    kbo = tmp_path / "kbo_rosters.txt"
    mlb.write_bytes(src.read_bytes())
    kbo.write_bytes(src.read_bytes())
    mlb_output = tmp_path / "mod_mlb_rosters.txt"
    kbo_output = tmp_path / "mod_kbo_rosters.txt"
    mlb_output.write_text("old mlb", encoding="utf-8")
    kbo_output.write_text("old kbo", encoding="utf-8")
    combined = load_combined_roster(mlb, kbo)
    real_replace = combined_module.os.replace
    replace_count = 0

    def fail_second_replace(source, destination):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("simulated second output failure")
        return real_replace(source, destination)

    monkeypatch.setattr(combined_module.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated second output failure"):
        save_modified_rosters_safely(combined)

    assert mlb_output.read_text(encoding="utf-8") == "old mlb"
    assert kbo_output.read_text(encoding="utf-8") == "old kbo"


def test_safe_save_refuses_to_overwrite_source_path(tmp_path: Path) -> None:
    source = tmp_path / "mod_mlb_rosters.txt"
    source.write_bytes((SAMPLE_DIR / "mlb_rosters.txt").read_bytes())
    before = source.read_bytes()
    combined = load_combined_roster(source, None)

    with pytest.raises(ValueError, match="Refusing to overwrite source roster"):
        save_modified_rosters_safely(combined)

    assert source.read_bytes() == before


def test_plan_reports_invalid_target_cell_and_rejects_stale_apply(
    sample_header,
) -> None:
    row = ["0"] * len(sample_header)
    row_set(row, sample_header, "id", "401")
    row_set(row, sample_header, "Position", "1")
    row_set(row, sample_header, "Contact vL", "invalid")
    row_set(row, sample_header, "Power vL", "100")
    player = CombinedPlayer(401, row, "mlb", 0, sample_header)
    settings = {
        401: PlayerBulkSettings(401, 30, False, base_fame=FameLevel.REGIONAL)
    }
    plan = build_bulk_rating_plan(
        [player], [401], settings, prospect_boost=False
    )

    assert plan.skipped_cell_count == 1
    assert plan.skipped_cells[0].header == "Contact vL"
    assert plan.skipped_cells[0].reason == "invalid numeric value"
    player.row[0] = "changed after preview"
    with pytest.raises(ValueError, match="Roster row changed after preview"):
        apply_bulk_rating_plan([player], plan)


def test_all_invalid_plan_has_no_changes_but_preserves_skip_details(
    sample_header,
) -> None:
    row = [""] * len(sample_header)
    row_set(row, sample_header, "id", "402")
    row_set(row, sample_header, "Position", "1")
    row_set(row, sample_header, "Contact vL", "not-a-number")
    player = CombinedPlayer(402, row, "mlb", 0, sample_header)
    settings = {
        402: PlayerBulkSettings(402, 30, False, base_fame=FameLevel.REGIONAL)
    }

    plan = build_bulk_rating_plan(
        [player], [402], settings, prospect_boost=False
    )

    assert plan.changes == ()
    assert plan.unchanged == ((402, "selected rule produced no cell changes"),)
    assert plan.skipped_cell_count == 1
    assert plan.skipped_cells[0].player_id == 402
    assert plan.skipped_cells[0].header == "Contact vL"
    assert plan.skipped_cells[0].reason == "invalid numeric value"


def test_no_changes_dialog_shows_skipped_player_and_invalid_cell_details(
    sample_header,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QApplication

    from gui.widgets import bulk_rating_dialog as dialog_module

    app = QApplication.instance() or QApplication([])
    row = [""] * len(sample_header)
    row_set(row, sample_header, "id", "402")
    row_set(row, sample_header, "Position", "1")
    row_set(row, sample_header, "Contact vL", "not-a-number")
    player = CombinedPlayer(402, row, "mlb", 0, sample_header)
    settings = {
        402: PlayerBulkSettings(402, 30, False, base_fame=FameLevel.REGIONAL)
    }
    plan = build_bulk_rating_plan(
        [player], [402, 999], settings, prospect_boost=False
    )
    captured: dict[str, str] = {}

    class FakeMessageBox:
        class Icon:
            Information = object()

        class StandardButton:
            Ok = object()

        def __init__(self, _parent) -> None:
            pass

        def setIcon(self, _icon) -> None:
            pass

        def setWindowTitle(self, title: str) -> None:
            captured["title"] = title

        def setText(self, text: str) -> None:
            captured["text"] = text

        def setDetailedText(self, text: str) -> None:
            captured["details"] = text

        def setStandardButtons(self, _buttons) -> None:
            pass

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(dialog_module, "QMessageBox", FakeMessageBox)
    fake_dialog = SimpleNamespace(_player_indices=[])
    fake_dialog._preview_text = lambda current_plan: (
        dialog_module.BulkRatingDialog._preview_text(fake_dialog, current_plan)
    )

    dialog_module.BulkRatingDialog._show_no_changes_plan(fake_dialog, plan)

    assert app is not None
    assert "1 players" in captured["text"]
    assert "1 invalid cells" in captured["text"]
    assert "999" in captured["details"]
    assert "player is not present in the roster" in captured["details"]
    assert "Contact vL" in captured["details"]
    assert "invalid numeric value" in captured["details"]
