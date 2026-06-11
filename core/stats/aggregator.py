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
                    data,
                    pitcher,
                    season,
                    away_pitch_events.get(pitcher.player_name),
                    data.away_pitching,
                )
            for pitcher in data.home_pitching:
                self._insert_pitching_log(
                    data,
                    pitcher,
                    season,
                    home_pitch_events.get(pitcher.player_name),
                    data.home_pitching,
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
        progress_callback: Any | None = None,
    ) -> BatchImportResult:
        directory = Path(boxscore_dir)
        if not directory.is_dir():
            return BatchImportResult(
                errors=[ImportResult(game_id=-1, error=f"Directory not found: {directory}")]
            )

        files = sorted(directory.glob(GAME_BOX_GLOB))
        known_ids = self.get_known_game_ids()
        result = BatchImportResult(total_scanned=len(files))

        for index, file_path in enumerate(files, start=1):
            if progress_callback:
                progress_callback(index, len(files), file_path.name)

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
                result.imported_game_ids.append(game_id)
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
        team_pitchers: list[PitcherLine],
    ) -> None:
        from core.stats.pitching_special import detect_special_game

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
        special = detect_special_game(
            pitcher, team_pitchers, data.meta, pitcher.team, data
        )

        self._conn.execute(
            """
            INSERT INTO pitching_logs (
                game_id, player_id, season, team, date,
                ip_outs, h, r, er, bb, k, hr, bf, pi,
                decision, win, loss, save, season_era,
                game_score, wild_pitch, hit_batsmen,
                is_cg, is_sho, is_no_hitter, is_perfect_game
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                special["is_cg"],
                special["is_sho"],
                special["is_no_hitter"],
                special["is_perfect_game"],
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
            f"""
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
                {_batting_ratio_sql()}
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
        max_init = self._get_max_init_season()
        row = self._conn.execute(
            f"""
            SELECT
                totals.player_id,
                p.short_name,
                p.full_name,
                totals.career_ab,
                totals.career_h,
                totals.career_hr,
                totals.career_rbi,
                totals.career_bb,
                totals.career_k,
                totals.career_doubles,
                totals.career_triples,
                totals.career_sb,
                ROUND(CAST(totals.career_h AS REAL) / NULLIF(totals.career_ab, 0), 3) AS career_avg,
                totals.career_games
            FROM ({_career_batting_union_sql(max_init)}) totals
            JOIN players p ON p.player_id = totals.player_id
            WHERE totals.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_pitching_season(self, player_id: int, season: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"""
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
                SUM(pl.is_cg) AS cg,
                SUM(pl.is_sho) AS sho,
                {_pitching_ratio_sql()}
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
            f"""
            SELECT
                totals.player_id,
                p.short_name,
                p.full_name,
                totals.career_ip_outs,
                totals.career_wins,
                totals.career_losses,
                totals.career_saves,
                totals.career_k,
                totals.career_er,
                ROUND(
                    CAST(totals.career_er * 27 AS REAL) / NULLIF(totals.career_ip_outs, 0), 2
                ) AS career_era,
                ROUND(
                    CAST(totals.career_bb + totals.career_ha AS REAL)
                    / NULLIF(totals.career_ip_outs / 3.0, 0), 3
                ) AS career_whip
            FROM ({_career_pitching_union_sql(self._get_max_init_season())}) totals
            JOIN players p ON p.player_id = totals.player_id
            WHERE totals.player_id = ?
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
            f"""
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
                {_batting_ratio_sql()}
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
            f"""
            SELECT
                totals.player_id AS id,
                p.short_name AS name,
                p.full_name,
                '' AS team,
                totals.career_ab AS ab,
                totals.career_h AS h,
                totals.career_r AS r,
                totals.career_rbi AS rbi,
                totals.career_bb AS bb,
                totals.career_k AS k,
                totals.career_hr AS hr,
                totals.career_sb AS sb,
                totals.career_doubles AS doubles,
                totals.career_triples AS triples,
                ROUND(CAST(totals.career_h AS REAL) / NULLIF(totals.career_ab, 0), 3) AS avg,
                totals.career_games AS career_games
            FROM ({_career_batting_union_sql(self._get_max_init_season())}) totals
            JOIN players p ON p.player_id = totals.player_id
            ORDER BY p.short_name
            """,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_season_pitching_totals(self, season: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"""
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
                {_pitching_ratio_sql()}
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
            f"""
            SELECT
                totals.player_id AS id,
                p.short_name AS name,
                p.full_name,
                '' AS team,
                totals.career_ip_outs AS ip_outs,
                totals.career_ha AS h,
                totals.career_er AS er,
                totals.career_bb AS bb,
                totals.career_k AS k,
                totals.career_hr AS hr,
                totals.career_wins AS w,
                totals.career_losses AS l,
                totals.career_saves AS sv,
                ROUND(
                    CAST(totals.career_er * 27 AS REAL) / NULLIF(totals.career_ip_outs, 0), 2
                ) AS era
            FROM ({_career_pitching_union_sql(self._get_max_init_season())}) totals
            JOIN players p ON p.player_id = totals.player_id
            ORDER BY p.short_name
            """,
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["ip"] = outs_to_ip_float(int(data["ip_outs"]))
            result.append(data)
        return result

    def get_career_batting_stat(self, player_id: int, stat: str) -> float:
        career = self.get_batting_career(player_id)
        if not career:
            return 0.0
        return float(career.get(stat, 0) or 0)

    def get_career_pitching_stat(self, player_id: int, stat: str) -> float:
        career = self.get_pitching_career(player_id)
        if not career:
            return 0.0
        return float(career.get(stat, 0) or 0)

    def get_game_contribution_batting(
        self, player_id: int, game_id: int, stat: str
    ) -> float:
        column = _BATTING_GAME_STAT_COLUMNS.get(stat, stat)
        row = self._conn.execute(
            f"SELECT {column} AS value FROM batting_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        return float(row["value"]) if row else 0.0

    def get_game_contribution_pitching(
        self, player_id: int, game_id: int, stat: str
    ) -> float:
        column = _PITCHING_GAME_STAT_COLUMNS.get(stat, stat)
        row = self._conn.execute(
            f"SELECT {column} AS value FROM pitching_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        return float(row["value"]) if row else 0.0

    def get_max_prior_season_stat(
        self, player_id: int, season: int, game_id: int, stat: str
    ) -> float | None:
        column = _SEASON_TRACKING_COLUMNS.get(stat)
        if not column:
            return None
        row = self._conn.execute(
            f"""
            SELECT MAX({column}) AS prior_value
            FROM batting_logs
            WHERE player_id = ? AND season = ? AND game_id <> ?
            """,
            (player_id, season, game_id),
        ).fetchone()
        if row and row["prior_value"] is not None:
            return float(row["prior_value"])
        return None

    def get_max_prior_season_pitching_stat(
        self, player_id: int, season: int, game_id: int, stat: str
    ) -> float:
        if stat == "season_k_pit":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(k), 0) AS prior_value
                FROM pitching_logs
                WHERE player_id = ? AND season = ? AND game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        if stat == "season_wins":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(win), 0) AS prior_value
                FROM pitching_logs
                WHERE player_id = ? AND season = ? AND game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        if stat == "season_saves":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(save), 0) AS prior_value
                FROM pitching_logs
                WHERE player_id = ? AND season = ? AND game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        return 0.0

    def _get_max_init_season(self) -> int:
        from core.db.meta import get_init_season_coverage

        return get_init_season_coverage(self._conn)

    def get_db_summary(self) -> dict[str, int]:
        games = self._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        players = self._conn.execute(
            """
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT player_id FROM batting_logs
                UNION
                SELECT player_id FROM pitching_logs
            )
            """
        ).fetchone()[0]
        return {"games": int(games), "players": int(players)}

    def get_available_seasons(self) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT season FROM (
                SELECT season FROM batting_logs
                UNION
                SELECT season FROM pitching_logs
            )
            ORDER BY season DESC
            """
        ).fetchall()
        return [int(row[0]) for row in rows]

    def get_tracked_players(self, tracked_teams: list[str] | None = None) -> list[dict[str, Any]]:
        teams = [team.strip() for team in (tracked_teams or []) if team.strip()]
        if not teams:
            rows = self._conn.execute(
                """
                SELECT
                    p.player_id,
                    p.full_name,
                    p.short_name,
                    EXISTS(
                        SELECT 1 FROM batting_logs b WHERE b.player_id = p.player_id
                    ) AS is_batter,
                    EXISTS(
                        SELECT 1 FROM pitching_logs pl WHERE pl.player_id = p.player_id
                    ) AS is_pitcher
                FROM players p
                WHERE p.player_id IN (
                    SELECT player_id FROM batting_logs
                    UNION
                    SELECT player_id FROM pitching_logs
                )
                ORDER BY p.full_name
                """
            ).fetchall()
        else:
            placeholders = ",".join("?" * len(teams))
            rows = self._conn.execute(
                f"""
                SELECT DISTINCT
                    p.player_id,
                    p.full_name,
                    p.short_name,
                    EXISTS(
                        SELECT 1 FROM batting_logs b2 WHERE b2.player_id = p.player_id
                    ) AS is_batter,
                    EXISTS(
                        SELECT 1 FROM pitching_logs pl2 WHERE pl2.player_id = p.player_id
                    ) AS is_pitcher
                FROM players p
                WHERE p.player_id IN (
                    SELECT player_id FROM batting_logs WHERE team IN ({placeholders})
                    UNION
                    SELECT player_id FROM pitching_logs WHERE team IN ({placeholders})
                )
                ORDER BY p.full_name
                """,
                teams + teams,
            ).fetchall()
        return [dict(row) for row in rows]

    def player_has_init_stats(self, player_id: int) -> bool:
        batting = self._conn.execute(
            "SELECT 1 FROM career_batting_init WHERE player_id = ? LIMIT 1",
            (player_id,),
        ).fetchone()
        pitching = self._conn.execute(
            "SELECT 1 FROM career_pitching_init WHERE player_id = ? LIMIT 1",
            (player_id,),
        ).fetchone()
        return batting is not None or pitching is not None

    def get_player_batting_game_logs(
        self, player_id: int, season: int
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                b.game_id,
                b.date,
                b.team,
                g.away_team,
                g.home_team,
                b.ab, b.h, b.home_runs AS hr, b.rbi, b.bb, b.k,
                b.doubles, b.triples, b.r, b.stolen_bases AS sb,
                b.season_avg
            FROM batting_logs b
            JOIN games g ON g.game_id = b.game_id
            WHERE b.player_id = ? AND b.season = ?
            ORDER BY b.date, b.game_id
            """,
            (player_id, season),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            if data["team"] == data["away_team"]:
                data["opponent"] = data["home_team"]
            else:
                data["opponent"] = data["away_team"]
            result.append(data)
        return result

    def get_player_pitching_game_logs(
        self, player_id: int, season: int
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                pl.game_id,
                pl.date,
                pl.team,
                g.away_team,
                g.home_team,
                pl.ip_outs,
                pl.h, pl.er, pl.bb, pl.k, pl.hr,
                pl.win, pl.loss, pl.save,
                pl.is_cg, pl.is_sho,
                pl.decision
            FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id
            WHERE pl.player_id = ? AND pl.season = ?
            ORDER BY pl.date, pl.game_id
            """,
            (player_id, season),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["ip"] = outs_to_ip_str(int(data["ip_outs"]))
            if data["team"] == data["away_team"]:
                data["opponent"] = data["home_team"]
            else:
                data["opponent"] = data["away_team"]
            result.append(data)
        return result

    def get_player_career_batting_row(self, player_id: int) -> dict[str, Any] | None:
        max_init = self._get_max_init_season()
        row = self._conn.execute(
            f"""
            SELECT
                totals.player_id,
                p.full_name,
                totals.career_games AS g,
                totals.career_ab AS ab,
                totals.career_h AS h,
                totals.career_doubles AS doubles,
                totals.career_triples AS triples,
                totals.career_hr AS hr,
                totals.career_rbi AS rbi,
                totals.career_r AS r,
                totals.career_bb AS bb,
                totals.career_k AS k,
                totals.career_sb AS sb,
                ROUND(CAST(totals.career_h AS REAL) / NULLIF(totals.career_ab, 0), 3) AS avg
            FROM ({_career_batting_union_sql(max_init)}) totals
            JOIN players p ON p.player_id = totals.player_id
            WHERE totals.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_player_career_pitching_row(self, player_id: int) -> dict[str, Any] | None:
        max_init = self._get_max_init_season()
        row = self._conn.execute(
            f"""
            SELECT
                totals.player_id,
                p.full_name,
                totals.career_ip_outs AS ip_outs,
                totals.career_ha AS h,
                totals.career_er AS er,
                totals.career_bb AS bb,
                totals.career_k AS k,
                totals.career_hr AS hr,
                totals.career_wins AS w,
                totals.career_losses AS l,
                totals.career_saves AS s,
                ROUND(
                    CAST(totals.career_er * 27 AS REAL) / NULLIF(totals.career_ip_outs, 0), 2
                ) AS era,
                ROUND(
                    CAST(totals.career_bb + totals.career_ha AS REAL)
                    / NULLIF(totals.career_ip_outs / 3.0, 0), 3
                ) AS whip
            FROM ({_career_pitching_union_sql(max_init)}) totals
            JOIN players p ON p.player_id = totals.player_id
            WHERE totals.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["ip"] = outs_to_ip_str(int(data["ip_outs"]))
        init = self._conn.execute(
            """
            SELECT COALESCE(SUM(g),0) AS g, COALESCE(SUM(gs),0) AS gs,
                   COALESCE(SUM(cg),0) AS cg, COALESCE(SUM(sho),0) AS sho
            FROM career_pitching_init WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()
        log_games = self._conn.execute(
            "SELECT COUNT(DISTINCT game_id) FROM pitching_logs WHERE player_id = ?",
            (player_id,),
        ).fetchone()[0]
        log_cg = self._conn.execute(
            "SELECT COALESCE(SUM(is_cg),0) FROM pitching_logs WHERE player_id = ?",
            (player_id,),
        ).fetchone()[0]
        log_sho = self._conn.execute(
            "SELECT COALESCE(SUM(is_sho),0) FROM pitching_logs WHERE player_id = ?",
            (player_id,),
        ).fetchone()[0]
        data["g"] = int(init[0]) + int(log_games)
        data["gs"] = int(init[1])
        data["cg"] = int(init[2]) + int(log_cg)
        data["sho"] = int(init[3]) + int(log_sho)
        return data

    def get_players_in_game(self, game_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT player_id, COALESCE(p.short_name, p.full_name) AS player_name
            FROM (
                SELECT player_id FROM batting_logs WHERE game_id = ?
                UNION
                SELECT player_id FROM pitching_logs WHERE game_id = ?
            ) ids
            JOIN players p ON p.player_id = ids.player_id
            """,
            (game_id, game_id),
        ).fetchall()
        return [dict(row) for row in rows]


_BATTING_GAME_STAT_COLUMNS = {
    "h": "h",
    "hr": "home_runs",
    "rbi": "rbi",
    "bb": "bb",
    "sb": "stolen_bases",
    "doubles": "doubles",
    "k_bat": "k",
}

_PITCHING_GAME_STAT_COLUMNS = {
    "k_pit": "k",
    "ip_outs": "ip_outs",
    "cg": "is_cg",
    "sho": "is_sho",
    "no_hitter": "is_no_hitter",
    "perfect_game": "is_perfect_game",
    "wins": "win",
    "saves": "save",
}

_SEASON_TRACKING_COLUMNS = {
    "season_hr": "season_hr",
    "season_h": "season_hr",  # fallback; season_h uses sum instead
    "season_rbi": "season_rbi",
    "season_sb": "season_hr",
}


def _batting_ratio_sql() -> str:
    return """
                ROUND(CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0), 3) AS avg,
                ROUND(
                    CAST(SUM(b.h) + SUM(b.bb) + SUM(b.hit_by_pitch) AS REAL)
                    / NULLIF(SUM(b.ab) + SUM(b.bb) + SUM(b.hit_by_pitch), 0), 3
                ) AS obp,
                ROUND(
                    CAST(
                        SUM(b.h - b.doubles - b.triples - b.home_runs)
                        + 2 * SUM(b.doubles)
                        + 3 * SUM(b.triples)
                        + 4 * SUM(b.home_runs)
                    AS REAL) / NULLIF(SUM(b.ab), 0), 3
                ) AS slg,
                ROUND(
                    (
                        CAST(SUM(b.h) + SUM(b.bb) + SUM(b.hit_by_pitch) AS REAL)
                        / NULLIF(SUM(b.ab) + SUM(b.bb) + SUM(b.hit_by_pitch), 0)
                    ) + (
                        CAST(
                            SUM(b.h - b.doubles - b.triples - b.home_runs)
                            + 2 * SUM(b.doubles)
                            + 3 * SUM(b.triples)
                            + 4 * SUM(b.home_runs)
                        AS REAL) / NULLIF(SUM(b.ab), 0)
                    ), 3
                ) AS ops,
    """


def _pitching_ratio_sql() -> str:
    return """
                ROUND(
                    CAST(SUM(pl.er) * 27 AS REAL) / NULLIF(SUM(pl.ip_outs), 0), 2
                ) AS era,
                ROUND(
                    CAST(SUM(pl.bb) + SUM(pl.h) AS REAL)
                    / NULLIF(SUM(pl.ip_outs) / 3.0, 0), 3
                ) AS whip,
    """


def _career_batting_union_sql(max_init_season: int) -> str:
    return f"""
        SELECT
            player_id,
            SUM(g) AS career_games,
            SUM(ab) AS career_ab,
            SUM(h) AS career_h,
            SUM(doubles) AS career_doubles,
            SUM(triples) AS career_triples,
            SUM(hr) AS career_hr,
            SUM(rbi) AS career_rbi,
            SUM(r) AS career_r,
            SUM(sb) AS career_sb,
            SUM(bb) AS career_bb,
            SUM(k) AS career_k
        FROM (
            SELECT player_id, g, ab, h, doubles, triples, hr, rbi, r, sb, bb, k
            FROM career_batting_init
            WHERE season <= {int(max_init_season)}
            UNION ALL
            SELECT
                player_id,
                COUNT(DISTINCT game_id) AS g,
                SUM(ab), SUM(h), SUM(doubles), SUM(triples), SUM(home_runs),
                SUM(rbi), SUM(r), SUM(stolen_bases), SUM(bb), SUM(k)
            FROM batting_logs
            GROUP BY player_id
        )
        GROUP BY player_id
    """


def _career_pitching_union_sql(max_init_season: int) -> str:
    return f"""
        SELECT
            player_id,
            SUM(ip_outs) AS career_ip_outs,
            SUM(w) AS career_wins,
            SUM(l) AS career_losses,
            SUM(s) AS career_saves,
            SUM(k) AS career_k,
            SUM(er) AS career_er,
            SUM(ha) AS career_ha,
            SUM(bb) AS career_bb,
            SUM(hr) AS career_hr
        FROM (
            SELECT player_id, ip_outs, w AS w, l AS l, s AS s, k, er, ha, bb, hr
            FROM career_pitching_init
            WHERE season <= {int(max_init_season)}
            UNION ALL
            SELECT
                player_id,
                SUM(ip_outs), SUM(win), SUM(loss), SUM(save), SUM(k),
                SUM(er), SUM(h), SUM(bb), SUM(hr)
            FROM pitching_logs
            GROUP BY player_id
        )
        GROUP BY player_id
    """


def _game_id_from_filename(filename: str) -> int:
    import re

    match = re.search(r"game_box_(\d+)\.html", filename, re.I)
    return int(match.group(1)) if match else -1
