"""Roster editor bulk-edit tests."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from core.roster.editor import RosterEditor, RosterFilter


@pytest.fixture
def roster_csv(tmp_path: Path) -> Path:
    path = tmp_path / "roster.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Name", "Team", "Position", "Age", "OVR"]
        )
        writer.writeheader()
        writer.writerow(
            {"Name": "A. Judge", "Team": "NYY", "Position": "RF", "Age": "33", "OVR": "78"}
        )
        writer.writerow(
            {"Name": "B. Player", "Team": "SF", "Position": "SP", "Age": "25", "OVR": "60"}
        )
        writer.writerow(
            {"Name": "C. Rookie", "Team": "SF", "Position": "CF", "Age": "21", "OVR": "45"}
        )
    return path


def test_filter_by_position_and_age(roster_csv: Path) -> None:
    editor = RosterEditor()
    editor.load(roster_csv)
    filtered = editor.filter_rows(RosterFilter(position="SP", min_age=24, max_age=30))
    assert len(filtered) == 1
    assert filtered[0]["Name"] == "B. Player"


def test_bulk_edit_set_and_add(roster_csv: Path) -> None:
    editor = RosterEditor()
    editor.load(roster_csv)
    rows = editor.filter_rows(RosterFilter(min_age=21, max_age=33))
    assert editor.bulk_edit(rows, "OVR", 70, mode="set") == 3

    editor.bulk_edit(rows, "OVR", 5, mode="add")
    reloaded = {row["Name"]: row["OVR"] for row in editor.snapshot_rows()}
    assert reloaded["A. Judge"] == "75"
    assert reloaded["B. Player"] == "75"
    assert reloaded["C. Rookie"] == "75"


def test_save_requires_backup_then_writes(roster_csv: Path, tmp_path: Path) -> None:
    editor = RosterEditor()
    editor.load(roster_csv)
    rows = editor.filter_rows(RosterFilter())
    editor.bulk_edit(rows[:1], "OVR", 80, mode="set")

    assert editor.backup_saved is False
    backup = editor.save_copy(roster_csv)
    assert backup.is_file()
    assert editor.backup_saved is True

    editor.save(roster_csv)
    editor2 = RosterEditor()
    editor2.load(roster_csv)
    names = {row["Name"]: row["OVR"] for row in editor2.snapshot_rows()}
    assert names["A. Judge"] == "80"
