"""Player display name helpers."""

from __future__ import annotations

from core.stats.player_display import (
    best_display_name,
    format_player_list_label,
    looks_abbreviated,
)


def test_looks_abbreviated() -> None:
    assert looks_abbreviated("J. Lee") is True
    assert looks_abbreviated("Jung-hoo Lee") is False


def test_best_display_name_prefers_full() -> None:
    assert best_display_name("J. Lee", "J. Lee") == "J. Lee"
    assert best_display_name("Jung-hoo Lee", "J. Lee") == "Jung-hoo Lee"


def test_list_label_includes_id_for_abbrev() -> None:
    label = format_player_list_label(
        {
            "player_id": 36442,
            "full_name": "J. Lee",
            "short_name": "J. Lee",
            "is_pitcher": True,
        }
    )
    assert "(#36442)" in label
    assert "[P]" in label
