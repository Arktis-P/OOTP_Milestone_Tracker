"""Position group filter tests."""

from __future__ import annotations

from core.roster.position_filter import matches_position_group, position_label


def test_position_labels() -> None:
    assert position_label("11") == "SP"
    assert position_label("2") == "C"


def test_position_groups() -> None:
    assert matches_position_group("4", "if")
    assert matches_position_group("8", "of")
    assert not matches_position_group("11", "if")
    assert matches_position_group("13", None)
