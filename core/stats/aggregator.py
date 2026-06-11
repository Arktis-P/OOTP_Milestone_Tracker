"""SQLite persistence and stat aggregation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.db.schema import init_database
from core.parser.batting_notes import get_player_event_counts
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.parser.common import ParserError
from core.parser.pitching_notes import get_player_pitching_counts
from core.stats.ip_utils import ip_to_outs, outs_to_ip_float, outs_to_ip_str
from core.stats.models import (
    BatchImportResult,
    BatterLine,
    BoxscoreData,
    ImportResult,
    PitcherLine,
)

GAME_BOX_GLOB = "game_box_*.html"


class Aggregator:
    """Persists box score data and provides aggregation queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_database(self.db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Aggregator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def game_exists(self, game_id: int) -> bool:
        return game_id in self.get_known_game_ids()

    def get_known_game_ids(self) -> set[int]:
        rows = self._conn.execute("SELECT game_id FROM games").fetchall()
        return {int(row["game_id"]) for row in rows}

    def upsert_player(self, player_id: int, short_name: str, full_name: str | None = None) -> None:
        display = full_name or short_name
        self._conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                short_name = COALESCE(excluded.short_name, players.short_name),
                full_name = CASE
                    WHEN length(excluded.full_name) > length(players.full_name)
                    THEN excluded.full_name
                    ELSE players.full_name
                END
            """,
            (player_id, display, short_name),
        )

    def import_boxscore(self, data: BoxscoreData, season: int) -> ImportResult:
        game_id = data.meta.game_id
        if self.game_exists(game_id):
            return ImportResult(game_id=game_id, skipped=True)

        try:
            self._conn.execute("BEGIN")
            self._insert_game(data, season)
            away_events = self._batting_events_for_team(data.away_batting_notes)
            home_events = self._batting_events_for_team(data.home_batting_notes)
            away_pitch_events = self._pitching_events_for_team(data.away_pitching_notes)
            home_pitch_events = self._pitching_events_for_team(data.home_pitching_notes)

            for batter in data.away_batting:
                self._insert_batting_log(
                    data, batter, season, away_events.get(batter.player_name)
                )
            for batter in data.home_batting:
                self._insert_batting_log(
                    data, batter, season, home_events.get(batter.player_name)
                )
            for pitcher in data.away_pitching:
                self._insert_pitching_log(
                    data, pitcher, season, away_pitch_events.get(pitcher.player_name)
                )
            for pitcher in data.home_pitching:
                self._insert_pitching_log(
                    data, pitcher, season, home_pitch_events.get(pitcher.player_name)
                )
            self._conn.commit()
            return ImportResult(game_id=game_id, skipped=False)
        except Exception as exc:
            self._conn.rollback()
            return ImportResult(game_id=game_id, skipped=False, error=str(exc))

    def import_all_new(
        self,
        boxscore_dir: str | Path,
        season: int,
        *,
        since_mtime: float | None = None,
    ) -> BatchImportResult:
        directory = Path(boxscore_dir)
        if not directory.is_dir():
            return BatchImportResult(
                errors=[ImportResult(game_id=-1, error=f"Directory not found: {directory}")]
            )

        files = sorted(directory.glob(GAME_BOX_GLOB))
        known_ids = self.get_known_game_ids()
        result = BatchImportResult(total_scanned=len(files))

        for file_path in files:
            if since_mtime is not None and file_path.stat().st_mtime <= since_mtime:
                result.skipped_mtime += 1
                continue

            game_id = _game_id_from_filename(file_path.name)
            if game_id < 0:
                result.errors.append(
                    ImportResult(game_id=game_id, error=f"Invalid filename: {file_path.name}")
                )
                continue

            if game_id in known_ids:
                result.skipped_existing += 1
                continue

            result.candidates += 1
            try:
                data = BoxscoreHTMLParser(file_path).parse()
                import_result = self.import_boxscore(data, season)
            except ParserError as exc:
                result.errors.append(ImportResult(game_id=game_id, error=str(exc)))
                continue
            except Exception as exc:
                result.errors.append(ImportResult(game_id=game_id, error=str(exc)))
                continue

            if import_result.error:
                result.errors.append(import_result)
            elif import_result.skipped:
                result.skipped += 1
                known_ids.add(game_id)
            else:
                result.imported += 1
                known_ids.add(game_id)

        return result

    def _insert_game(self, data: BoxscoreData, season: int) -> None:
        meta = data.meta
        notes = data.game_notes
        self._conn.execute(
            """
            INSERT INTO games (
                game_id, date, season, away_team, home_team,
                away_score, home_score, away_innings, home_innings,
                away_hits, home_hits, away_errors, home_errors,
                ballpark, attendance, game_time, weather,
                player_of_game_id, player_of_game_name, special_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta.game_id,
                meta.date,
                season,
                meta.away_team,
                meta.home_team,
                meta.away_score,
                meta.home_score,
                json.dumps(meta.away_innings),
                json.dumps(meta.home_innings),
                meta.away_hits,
                meta.home_hits,
                meta.away_errors,
                meta.home_errors,
                notes.ballpark or meta.ballpark,
                notes.attendance or meta.attendance,
                notes.game_time or meta.game_time,
                notes.weather,
                notes.player_of_game_id,
                notes.player_of_game,
                notes.special_notes,
            ),
        )

    def _insert_batting_log(
        self,
        data: BoxscoreData,
        batter: BatterLine,
        season: int,
        events=None,
    ) -> None:
        self.upsert_player(batter.player_id, batter.player_name)
        if events is None:
            note_text = (
                data.away_batting_notes
                if batter.team == data.meta.away_team
                else data.home_batting_notes
            )
            event_counts = get_player_event_counts(note_text, batter.player_name)
        else:
            event_counts = events
        self._conn.execute(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, date,
                ab, r, h, rbi, bb, k, lob,
                season_avg, season_hr, season_rbi,
                doubles, triples, home_runs, stolen_bases, hit_by_pitch, gidp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.meta.game_id,
                batter.player_id,
                season,
                batter.team,
                data.meta.date,
                batter.ab,
                batter.r,
                batter.h,
                batter.rbi,
                batter.bb,
                batter.k,
                batter.lob,
                batter.avg,
                batter.season_hr,
                batter.season_rbi,
                event_counts.doubles,
                event_counts.triples,
                event_counts.home_runs,
                event_counts.stolen_bases,
                event_counts.hit_by_pitch,
                event_counts.gidp,
            ),
        )

    def _insert_pitching_log(
        self,
        data: BoxscoreData,
        pitcher: PitcherLine,
        season: int,
        pitch_events,
    ) -> None:
        self.upsert_player(pitcher.player_id, pitcher.player_name)
        notes_text = (
            data.away_pitching_notes
            if pitcher.team == data.meta.away_team
            else data.home_pitching_notes
        )
        events = pitch_events or get_player_pitching_counts(notes_text, pitcher.player_name)
        win = 1 if pitcher.decision == "W" else 0
        loss = 1 if pitcher.decision == "L" else 0
        save = 1 if pitcher.decision == "S" else 0

        self._conn.execute(
            """
            INSERT INTO pitching_logs (
                game_id, player_id, season, team, date,
                ip_outs, h, r, er, bb, k, hr, bf, pi,
                decision, win, loss, save, season_era,
                game_score, wild_pitch, hit_batsmen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.meta.game_id,
                pitcher.player_id,
                season,
                pitcher.team,
                data.meta.date,
                ip_to_outs(pitcher.ip),
                pitcher.h,
                pitcher.r,
                pitcher.er,
                pitcher.bb,
                pitcher.k,
                pitcher.hr,
                pitcher.bf,
                pitcher.pi,
                pitcher.decision or None,
                win,
                loss,
                save,
                pitcher.era,
                events.game_score,
                events.wild_pitch,
                events.hit_batsmen,
            ),
        )

    @staticmethod
    def _batting_events_for_team(note_text: str) -> dict:
        from core.parser.batting_notes import parse_team_batting_notes

        return parse_team_batting_notes(note_text)

    @staticmethod
    def _pitching_events_for_team(note_text: str) -> dict:
        from core.parser.pitching_notes import parse_team_pitching_notes

        return parse_team_pitching_notes(note_text)

    def get_batting_season(self, player_id: int, season: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                b.player_id,
                p.short_name,
                p.full_name,
                SUM(b.ab) AS ab,
                SUM(b.h) AS h,
                SUM(b.r) AS r,
                SUM(b.rbi) AS rbi,
                SUM(b.bb) AS bb,
                SUM(b.k) AS k,
                SUM(b.doubles) AS doubles,
                SUM(b.triples) AS triples,
                SUM(b.home_runs) AS hr,
                SUM(b.stolen_bases) AS sb,
                SUM(b.hit_by_pitch) AS hbp,
                ROUND(CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0), 3) AS avg,
                COUNT(DISTINCT b.game_id) AS games_played
            FROM batting_logs b
            JOIN players p ON p.player_id = b.player_id
            WHERE b.season = ? AND b.player_id = ?
            GROUP BY b.player_id
            """,
            (season, player_id),
        ).fetchone()
        return dict(row) if row else None

    def get_batting_career(self, player_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                b.player_id,
                p.short_name,
                p.full_name,
                SUM(b.ab) AS career_ab,
                SUM(b.h) AS career_h,
                SUM(b.home_runs) AS career_hr,
                SUM(b.rbi) AS career_rbi,
                SUM(b.bb) AS career_bb,
                SUM(b.k) AS career_k,
                SUM(b.doubles) AS career_doubles,
                SUM(b.triples) AS career_triples,
                SUM(b.stolen_bases) AS career_sb,
                ROUND(CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0), 3) AS career_avg,
                COUNT(DISTINCT b.game_id) AS career_games
            FROM batting_logs b
            JOIN players p ON p.player_id = b.player_id
            WHERE b.player_id = ?
            GROUP BY b.player_id
            """,
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_pitching_season(self, player_id: int, season: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                pl.player_id,
                p.short_name,
                p.full_name,
                SUM(pl.ip_outs) AS ip_outs,
                SUM(pl.h) AS h,
                SUM(pl.er) AS er,
                SUM(pl.bb) AS bb,
                SUM(pl.k) AS k,
                SUM(pl.hr) AS hr,
                SUM(pl.win) AS wins,
                SUM(pl.loss) AS losses,
                SUM(pl.save) AS saves,
                ROUND(
                    CAST(SUM(pl.er) * 27 AS REAL) / NULLIF(SUM(pl.ip_outs), 0), 2
                ) AS era,
                COUNT(DISTINCT pl.game_id) AS games
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            WHERE pl.season = ? AND pl.player_id = ?
            GROUP BY pl.player_id
            """,
            (season, player_id),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["ip"] = outs_to_ip_float(int(data["ip_outs"]))
        data["ip_display"] = outs_to_ip_str(int(data["ip_outs"]))
        return data

    def get_pitching_career(self, player_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                pl.player_id,
                p.short_name,
                p.full_name,
                SUM(pl.ip_outs) AS career_ip_outs,
                SUM(pl.win) AS career_wins,
                SUM(pl.loss) AS career_losses,
                SUM(pl.save) AS career_saves,
                SUM(pl.k) AS career_k,
                SUM(pl.er) AS career_er,
                ROUND(
                    CAST(SUM(pl.er) * 27 AS REAL) / NULLIF(SUM(pl.ip_outs), 0), 2
                ) AS career_era
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            WHERE pl.player_id = ?
            GROUP BY pl.player_id
            """,
            (player_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["career_ip"] = outs_to_ip_float(int(data["career_ip_outs"]))
        data["career_ip_display"] = outs_to_ip_str(int(data["career_ip_outs"]))
        return data

    def get_career_stats(self, player_id: int) -> dict[str, Any]:
        return {
            "batting": self.get_batting_career(player_id),
            "pitching": self.get_pitching_career(player_id),
        }

    def get_game_stats(self, player_id: int, game_id: int) -> dict[str, Any]:
        batting = self._conn.execute(
            "SELECT * FROM batting_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        pitching = self._conn.execute(
            "SELECT * FROM pitching_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        result: dict[str, Any] = {"batting": None, "pitching": None}
        if batting:
            result["batting"] = dict(batting)
        if pitching:
            pitch = dict(pitching)
            pitch["ip_display"] = outs_to_ip_str(int(pitch["ip_outs"]))
            result["pitching"] = pitch
        return result

    def get_season_batting_totals(self, season: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                b.player_id AS id,
                p.short_name AS name,
                p.full_name,
                MAX(b.team) AS team,
                SUM(b.ab) AS ab,
                SUM(b.h) AS h,
                SUM(b.r) AS r,
                SUM(b.rbi) AS rbi,
                SUM(b.bb) AS bb,
                SUM(b.k) AS k,
                SUM(b.home_runs) AS hr,
                SUM(b.stolen_bases) AS sb,
                SUM(b.doubles) AS doubles,
                SUM(b.triples) AS triples,
                ROUND(CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0), 3) AS avg,
                COUNT(DISTINCT b.game_id) AS games_played
            FROM batting_logs b
            JOIN players p ON p.player_id = b.player_id
            WHERE b.season = ?
            GROUP BY b.player_id
            ORDER BY p.short_name
            """,
            (season,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_career_batting_totals(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                b.player_id AS id,
                p.short_name AS name,
                p.full_name,
                MAX(b.team) AS team,
                SUM(b.ab) AS ab,
                SUM(b.h) AS h,
                SUM(b.r) AS r,
                SUM(b.rbi) AS rbi,
                SUM(b.bb) AS bb,
                SUM(b.k) AS k,
                SUM(b.home_runs) AS hr,
                SUM(b.stolen_bases) AS sb,
                SUM(b.doubles) AS doubles,
                SUM(b.triples) AS triples,
                ROUND(CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0), 3) AS avg,
                COUNT(DISTINCT b.game_id) AS career_games
            FROM batting_logs b
            JOIN players p ON p.player_id = b.player_id
            GROUP BY b.player_id
            ORDER BY p.short_name
            """,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_season_pitching_totals(self, season: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                pl.player_id AS id,
                p.short_name AS name,
                p.full_name,
                MAX(pl.team) AS team,
                SUM(pl.ip_outs) AS ip_outs,
                SUM(pl.h) AS h,
                SUM(pl.er) AS er,
                SUM(pl.bb) AS bb,
                SUM(pl.k) AS k,
                SUM(pl.hr) AS hr,
                SUM(pl.win) AS w,
                SUM(pl.loss) AS l,
                SUM(pl.save) AS sv,
                ROUND(
                    CAST(SUM(pl.er) * 27 AS REAL) / NULLIF(SUM(pl.ip_outs), 0), 2
                ) AS era,
                COUNT(DISTINCT pl.game_id) AS games
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            WHERE pl.season = ?
            GROUP BY pl.player_id
            ORDER BY p.short_name
            """,
            (season,),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["ip"] = outs_to_ip_float(int(data["ip_outs"]))
            result.append(data)
        return result

    def get_career_pitching_totals(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                pl.player_id AS id,
                p.short_name AS name,
                p.full_name,
                MAX(pl.team) AS team,
                SUM(pl.ip_outs) AS ip_outs,
                SUM(pl.h) AS h,
                SUM(pl.er) AS er,
                SUM(pl.bb) AS bb,
                SUM(pl.k) AS k,
                SUM(pl.hr) AS hr,
                SUM(pl.win) AS w,
                SUM(pl.loss) AS l,
                SUM(pl.save) AS sv,
                ROUND(
                    CAST(SUM(pl.er) * 27 AS REAL) / NULLIF(SUM(pl.ip_outs), 0), 2
                ) AS era
            FROM pitching_logs pl
            JOIN players p ON p.player_id = pl.player_id
            GROUP BY pl.player_id
            ORDER BY p.short_name
            """,
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["ip"] = outs_to_ip_float(int(data["ip_outs"]))
            result.append(data)
        return result


def _game_id_from_filename(filename: str) -> int:
    import re

    match = re.search(r"game_box_(\d+)\.html", filename, re.I)
    return int(match.group(1)) if match else -1
