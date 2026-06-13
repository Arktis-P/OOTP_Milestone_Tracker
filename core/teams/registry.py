"""OOTP team_id registry — seeded from stats export, updated from boxscores when changed."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from core.stats.team_filter import (
    CANONICAL_MLB_TEAMS,
    MLB_TEAM_ALIASES,
    is_ootp_mlb_league_row,
)


@dataclass
class TeamSyncResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> int:
        return self.inserted + self.updated


class TeamRegistry:
    """Maps OOTP ``team_id`` to abbr/name; upserts only when data changes."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(
        self,
        team_id: int,
        *,
        team_abbr: str = "",
        team_name: str = "",
        league_abbr: str = "MLB",
        source: str = "",
    ) -> str:
        abbr = str(team_abbr or "").strip()
        name = str(team_name or "").strip()
        league = str(league_abbr or "MLB").strip() or "MLB"
        src = str(source or "").strip()

        row = self.conn.execute(
            """
            SELECT team_id, team_abbr, team_name, league_abbr, source
            FROM teams
            WHERE team_id = ?
            """,
            (team_id,),
        ).fetchone()

        if not row:
            self.conn.execute(
                """
                INSERT INTO teams (
                    team_id, team_abbr, team_name, league_abbr, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (team_id, abbr, name, league, src),
            )
            return "inserted"

        new_abbr = abbr or str(row["team_abbr"] or "")
        new_name = name or str(row["team_name"] or "")
        new_league = league or str(row["league_abbr"] or "MLB")
        new_source = self._merge_source(str(row["source"] or ""), src)

        if (
            new_abbr == str(row["team_abbr"] or "")
            and new_name == str(row["team_name"] or "")
            and new_league == str(row["league_abbr"] or "MLB")
            and new_source == str(row["source"] or "")
        ):
            return "unchanged"

        self.conn.execute(
            """
            UPDATE teams
            SET team_abbr = ?, team_name = ?, league_abbr = ?, source = ?,
                updated_at = datetime('now')
            WHERE team_id = ?
            """,
            (new_abbr, new_name, new_league, new_source, team_id),
        )
        return "updated"

    def sync_from_export_rows(self, rows: list[dict[str, Any]]) -> TeamSyncResult:
        """Bulk seed/update from OOTP player stats export rows."""
        by_id: dict[int, dict[str, str]] = {}
        for row in rows:
            if not is_ootp_mlb_league_row(row):
                continue
            team_id = int(row.get("team_id") or 0)
            if team_id <= 0:
                continue
            abbr = str(row.get("team_abbr") or "").strip()
            name = str(row.get("team_name") or "").strip()
            league = str(row.get("league_abbr") or "MLB").strip() or "MLB"
            existing = by_id.get(team_id)
            if existing is None:
                by_id[team_id] = {
                    "team_abbr": abbr,
                    "team_name": name,
                    "league_abbr": league,
                }
                continue
            if abbr and not existing["team_abbr"]:
                existing["team_abbr"] = abbr
            if name and (not existing["team_name"] or len(name) > len(existing["team_name"])):
                existing["team_name"] = name

        result = TeamSyncResult()
        for team_id, info in sorted(by_id.items()):
            status = self.upsert(
                team_id,
                team_abbr=info["team_abbr"],
                team_name=info["team_name"],
                league_abbr=info["league_abbr"],
                source="export",
            )
            if status == "inserted":
                result.inserted += 1
            elif status == "updated":
                result.updated += 1
            else:
                result.unchanged += 1
        return result

    def sync_from_boxscore_meta(
        self,
        *,
        away_team: str,
        home_team: str,
        away_team_id: int | None = None,
        home_team_id: int | None = None,
    ) -> TeamSyncResult:
        """Update registry from one boxscore game (only if IDs/names changed)."""
        result = TeamSyncResult()
        pairs = (
            (away_team_id, away_team),
            (home_team_id, home_team),
        )
        for team_id, team_name in pairs:
            if not team_id:
                continue
            status = self.upsert(
                int(team_id),
                team_name=str(team_name or "").strip(),
                source="boxscore",
            )
            if status == "inserted":
                result.inserted += 1
            elif status == "updated":
                result.updated += 1
            else:
                result.unchanged += 1
        return result

    def resolve_id(self, team: str) -> int | None:
        """Resolve a team name or abbr to ``team_id`` using the registry."""
        token = str(team or "").strip()
        if not token:
            return None

        row = self.conn.execute(
            """
            SELECT team_id FROM teams
            WHERE team_abbr = ? OR team_name = ?
            LIMIT 1
            """,
            (token, token),
        ).fetchone()
        if row:
            return int(row["team_id"])

        canonical = CANONICAL_MLB_TEAMS.get(token.upper())
        if canonical:
            row = self.conn.execute(
                "SELECT team_id FROM teams WHERE team_name = ? LIMIT 1",
                (canonical,),
            ).fetchone()
            if row:
                return int(row["team_id"])

        for abbr, full_name in CANONICAL_MLB_TEAMS.items():
            if token == full_name or token in MLB_TEAM_ALIASES.get(abbr, ()):
                row = self.conn.execute(
                    """
                    SELECT team_id FROM teams
                    WHERE team_abbr = ? OR team_name = ?
                    LIMIT 1
                    """,
                    (abbr, full_name),
                ).fetchone()
                if row:
                    return int(row["team_id"])
        return None

    def team_name(self, team_id: int | None) -> str:
        if not team_id:
            return ""
        row = self.conn.execute(
            "SELECT team_name, team_abbr FROM teams WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        if not row:
            return ""
        return str(row["team_name"] or row["team_abbr"] or "")

    @staticmethod
    def _merge_source(existing: str, incoming: str) -> str:
        if not incoming:
            return existing
        if not existing:
            return incoming
        parts = {part.strip() for part in f"{existing},{incoming}".split(",") if part.strip()}
        return ",".join(sorted(parts))
