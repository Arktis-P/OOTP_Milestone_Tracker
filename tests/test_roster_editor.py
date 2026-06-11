"""Roster editor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.roster.editor import RosterEditor, RosterFilter
from core.roster.ootp_format import load_ootp_roster, player_age
from core.roster.row_access import row_get, row_set


def _write_ootp_roster(path: Path, rows: list[list[str]]) -> None:
    header = (
        "//id,del,team_id,Team Name,League Name,LastName,FirstName,NickName,"
        "UniformNumber,DayOB,MonthOB,YearOB,NationalityID,Nation,Position,"
        "Contact vL,Power vL,Stuff Overall,HBP,HBP"
    )
    lines = [
        "// List of Teams and their ID's:",
        header,
        "//NOTE: test file",
    ]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def roster_txt(tmp_path: Path) -> Path:
    path = tmp_path / "mlb_rosters.txt"
    _write_ootp_roster(
        path,
        [
            [
                "1",
                "0",
                "3",
                "Yankees",
                "MLB",
                "Judge",
                "Aaron",
                "",
                "99",
                "26",
                "4",
                "1992",
                "206",
                "USA",
                "9",
                "78",
                "85",
                "0",
                "5",
                "1",
            ],
            [
                "2",
                "0",
                "3",
                "Yankees",
                "MLB",
                "Cole",
                "Gerrit",
                "",
                "45",
                "8",
                "9",
                "1990",
                "206",
                "USA",
                "11",
                "20",
                "20",
                "72",
                "3",
                "2",
            ],
            [
                "3",
                "0",
                "4",
                "Red Sox",
                "MLB",
                "Rookie",
                "Kid",
                "",
                "1",
                "1",
                "1",
                "2005",
                "206",
                "USA",
                "8",
                "45",
                "40",
                "0",
                "0",
                "0",
            ],
        ],
    )
    return path


def test_load_ootp_roster_parses_rows(roster_txt: Path) -> None:
    roster = load_ootp_roster(roster_txt)
    assert len(roster.rows) == 3
    assert row_get(roster.rows[0], roster.fieldnames, "LastName") == "Judge"


def test_filter_by_position_group_and_age(roster_txt: Path) -> None:
    editor = RosterEditor()
    editor.set_season_year(2026)
    editor.load(roster_txt)
    filtered = editor.filter_rows(
        RosterFilter(position_group="sp", season_year=2026)
    )
    assert len(filtered) == 1
    assert row_get(filtered[0], editor.fieldnames, "LastName") == "Cole"

    young = editor.filter_rows(RosterFilter(max_age=22, season_year=2026))
    assert len(young) == 1
    assert row_get(young[0], editor.fieldnames, "LastName") == "Rookie"
    assert player_age(young[0], season_year=2026, fieldnames=editor.fieldnames) == 21


def test_row_set_duplicate_hbp(roster_txt: Path) -> None:
    editor = RosterEditor()
    editor.load(roster_txt)
    row = editor.snapshot_rows()[0]
    row_set(row, editor.fieldnames, "HBP", "9", occurrence=0)
    row_set(row, editor.fieldnames, "HBP", "4", occurrence=1)
    assert row_get(row, editor.fieldnames, "HBP", occurrence=0) == "9"
    assert row_get(row, editor.fieldnames, "HBP", occurrence=1) == "4"


def test_individual_field_edit_and_save(roster_txt: Path) -> None:
    editor = RosterEditor()
    editor.load(roster_txt)
    judge = next(
        r
        for r in editor.filter_rows(RosterFilter())
        if row_get(r, editor.fieldnames, "LastName") == "Judge"
    )
    row_set(judge, editor.fieldnames, "Contact vL", "80")
    editor.save_copy(roster_txt)
    editor.save(roster_txt)

    reloaded = RosterEditor()
    reloaded.load(roster_txt)
    judge = next(
        r
        for r in reloaded.snapshot_rows()
        if row_get(r, reloaded.fieldnames, "LastName") == "Judge"
    )
    assert row_get(judge, reloaded.fieldnames, "Contact vL") == "80"
    text = roster_txt.read_text(encoding="utf-8")
    assert text.startswith("// List of Teams")
