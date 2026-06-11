"""Row index access tests."""

from __future__ import annotations

from core.roster.row_access import field_index, row_get, row_set


def test_duplicate_column_occurrence() -> None:
    fieldnames = ["id", "HBP", "name", "HBP"]
    row = ["1", "10", "Player", "3"]
    assert field_index(fieldnames, "HBP", 0) == 1
    assert field_index(fieldnames, "HBP", 1) == 3
    assert row_get(row, fieldnames, "HBP", 0) == "10"
    assert row_get(row, fieldnames, "HBP", 1) == "3"
    row_set(row, fieldnames, "HBP", "99", occurrence=1)
    assert row[3] == "99"
