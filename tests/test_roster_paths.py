"""Roster export path resolution tests."""

from __future__ import annotations

from pathlib import Path

from core.roster.paths import expected_roster_path, find_roster_file


def test_find_roster_file_csv(tmp_path: Path) -> None:
    export_dir = tmp_path / "import_export"
    export_dir.mkdir()
    roster = export_dir / "mlb_rosters.csv"
    roster.write_text("Name,Team\nA,NY\n", encoding="utf-8")
    assert find_roster_file(export_dir, "mlb") == roster


def test_find_roster_file_bare_name(tmp_path: Path) -> None:
    export_dir = tmp_path / "import_export"
    export_dir.mkdir()
    roster = export_dir / "kbo_rosters"
    roster.write_text("Name,Team\nB,SF\n", encoding="utf-8")
    assert find_roster_file(export_dir, "kbo") == roster


def test_find_roster_file_missing(tmp_path: Path) -> None:
    export_dir = tmp_path / "import_export"
    export_dir.mkdir()
    assert find_roster_file(export_dir, "mlb") is None
    assert expected_roster_path(export_dir, "mlb") == export_dir / "mlb_rosters"
