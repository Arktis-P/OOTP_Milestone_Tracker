"""Manual player registration and merge with imported OOTP players."""

from __future__ import annotations

import re
from typing import Any

from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.player_display import looks_abbreviated

_NAME_SUFFIX_RE = re.compile(r"\s*\(#\d+\)\s*$")
_NAME_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")


def derive_short_name(full_name: str) -> str:
    """Build boxscore-style short name from a full name (e.g. Dong-ju Moon -> D. Moon)."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name.strip()
    first, last = parts[0], parts[-1]
    if not first or not last:
        return full_name.strip()
    return f"{first[0].upper()}. {last}"


def normalize_player_name(name: str) -> str:
    text = _NAME_PREFIX_RE.sub("", name.strip())
    text = _NAME_SUFFIX_RE.sub("", text).strip()
    return re.sub(r"\s+", " ", text).lower()


def name_match_keys(full_name: str, short_name: str | None = None) -> set[str]:
    keys: set[str] = set()
    full = full_name.strip()
    short = (short_name or "").strip()
    if full:
        keys.add(normalize_player_name(full))
        keys.add(normalize_player_name(derive_short_name(full)))
    if short:
        keys.add(normalize_player_name(short))
    return {key for key in keys if key}


def names_refer_to_same_person(
    left_full: str,
    left_short: str | None,
    right_full: str,
    right_short: str | None,
) -> bool:
    left_keys = name_match_keys(left_full, left_short)
    right_keys = name_match_keys(right_full, right_short)
    return bool(left_keys & right_keys)


class PlayerRegistry:
    """Register manual players and merge them when real imports appear."""

    def __init__(self, aggregator: Aggregator) -> None:
        self.aggregator = aggregator

    @property
    def conn(self) -> Any:
        return self.aggregator.conn

    def list_manual_players(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT player_id, full_name, short_name
            FROM players
            WHERE is_manual = 1
            ORDER BY full_name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_manual_player(self, full_name: str) -> int:
        cleaned = normalize_player_name(full_name)
        if not cleaned:
            raise ValueError(tr("Please enter a player name."))

        display_name = _NAME_PREFIX_RE.sub("", full_name.strip())
        display_name = _NAME_SUFFIX_RE.sub("", display_name).strip()
        if not display_name:
            raise ValueError(tr("Please enter a player name."))

        existing = self._find_existing_player(display_name)
        if existing is not None:
            return existing

        player_id = self._allocate_manual_player_id()
        short_name = derive_short_name(display_name)
        self.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name, is_manual)
            VALUES (?, ?, ?, 1)
            """,
            (player_id, display_name, short_name),
        )
        self.conn.commit()
        return player_id

    def resolve_player(self, name: str) -> int | None:
        return self._find_existing_player(name)

    def ensure_player(self, name: str) -> int:
        """Resolve an existing player or create a manual stub."""
        existing = self._find_existing_player(name)
        if existing is not None:
            return existing
        display = _NAME_PREFIX_RE.sub("", name.strip())
        display = _NAME_SUFFIX_RE.sub("", display).strip()
        return self.add_manual_player(display)

    def try_merge_on_import(
        self,
        player_id: int,
        *,
        short_name: str,
        full_name: str | None = None,
    ) -> list[int]:
        """Merge manual stubs that refer to the same person as an imported player."""
        if player_id <= 0:
            return []

        real_full = (full_name or short_name).strip()
        real_short = short_name.strip()
        manual_rows = self.conn.execute(
            """
            SELECT player_id, full_name, short_name
            FROM players
            WHERE is_manual = 1
            """
        ).fetchall()
        merged: list[int] = []
        for row in manual_rows:
            manual_id = int(row["player_id"])
            if not names_refer_to_same_person(
                str(row["full_name"]),
                str(row["short_name"] or ""),
                real_full,
                real_short,
            ):
                continue
            self._merge_manual_into_real(manual_id, player_id)
            merged.append(manual_id)
        return merged

    def _find_existing_player(self, name: str) -> int | None:
        from core.milestone.manual_entry import resolve_player_id

        player_id = resolve_player_id(self.conn, name)
        if player_id is not None:
            return player_id

        cleaned = _NAME_PREFIX_RE.sub("", name.strip())
        cleaned = _NAME_SUFFIX_RE.sub("", cleaned).strip()
        if not cleaned:
            return None

        rows = self.conn.execute(
            """
            SELECT player_id, full_name, short_name
            FROM players
            """
        ).fetchall()
        probe_keys = name_match_keys(cleaned, derive_short_name(cleaned))
        for row in rows:
            keys = name_match_keys(
                str(row["full_name"]),
                str(row["short_name"] or ""),
            )
            if keys & probe_keys:
                return int(row["player_id"])
        return None

    def _allocate_manual_player_id(self) -> int:
        row = self.conn.execute(
            "SELECT MIN(player_id) AS min_id FROM players WHERE is_manual = 1"
        ).fetchone()
        min_id = row["min_id"] if row else None
        if min_id is not None and int(min_id) < 0:
            return int(min_id) - 1
        return -1

    def _merge_manual_into_real(self, manual_id: int, real_id: int) -> None:
        if manual_id == real_id:
            return

        manual = self.conn.execute(
            "SELECT full_name, short_name FROM players WHERE player_id = ?",
            (manual_id,),
        ).fetchone()
        real = self.conn.execute(
            "SELECT full_name, short_name FROM players WHERE player_id = ?",
            (real_id,),
        ).fetchone()
        if manual is None or real is None:
            return

        manual_full = str(manual["full_name"]).strip()
        real_full = str(real["full_name"]).strip()
        merged_full = manual_full
        if real_full and not looks_abbreviated(real_full):
            if looks_abbreviated(manual_full) or len(real_full) >= len(manual_full):
                merged_full = real_full
        merged_short = str(real["short_name"] or derive_short_name(merged_full)).strip()
        if not merged_short:
            merged_short = derive_short_name(merged_full)

        tables_with_player_id = (
            "milestone_records",
            "milestone_predictions",
            "batting_logs",
            "pitching_logs",
            "player_roster",
            "player_team_affiliations",
            "career_batting_init",
            "career_pitching_init",
            "player_streaks",
        )
        for table in tables_with_player_id:
            if not self._table_exists(table):
                continue
            self.conn.execute(
                f"UPDATE {table} SET player_id = ? WHERE player_id = ?",
                (real_id, manual_id),
            )

        self.conn.execute(
            """
            UPDATE players
            SET full_name = ?, short_name = ?
            WHERE player_id = ?
            """,
            (merged_full, merged_short, real_id),
        )
        self.conn.execute("DELETE FROM players WHERE player_id = ?", (manual_id,))
        self.conn.commit()

    def _table_exists(self, table: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
        return row is not None
