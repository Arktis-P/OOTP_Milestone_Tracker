"""SQLite persistence and stat aggregation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.db.schema import init_database
from core.db.sqlite_config import configure_sqlite_connection
from core.parser.batting_notes import (
    BattingEventCounts,
    assign_batting_events_to_lineup,
    grand_slam_player_ids_for_lineup,
)
from core.parser.boxscore_html import (
    BoxscoreHTMLParser,
    GAME_BOX_GLOB,
    peek_is_mlb_boxscore,
)
from core.parser.common import ParserError
from core.parser.pitching_notes import get_player_pitching_counts
from core.stats.ip_utils import ip_to_outs, outs_to_ip_float, outs_to_ip_str
from core.stats.team_filter import build_tracked_team_match_sql, expand_tracked_teams
from core.stats.models import (
    BatchImportResult,
    BatterLine,
    BoxscoreData,
    ImportResult,
    PitcherLine,
)

_MLB_GAME_JOIN_B = "JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1"
_MLB_GAME_JOIN_PL = "JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1"


class Aggregator:
    """Persists box score data and provides aggregation queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_database(self.db_path)
        self._conn: sqlite3.Connection | None = self._open_connection()

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        configure_sqlite_connection(conn)
        return conn

    @property
    def is_closed(self) -> bool:
        return self._conn is None

    def reopen(self) -> None:
        """Close and reopen the connection (e.g. after DB file reset)."""
        self.close()
        if not self.db_path.is_file():
            init_database(self.db_path)
        self._conn = self._open_connection()

    def switch_database(self, db_path: str | Path) -> None:
        """Point at another save DB file and reopen the connection."""
        self.db_path = Path(db_path)
        self.reopen()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        return self._conn

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    def __enter__(self) -> Aggregator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def game_exists(self, game_id: int) -> bool:
        return game_id in self.get_known_game_ids()

    def delete_game_import_data(self, game_id: int) -> bool:
        """Remove one imported game so it can be re-imported."""
        if not self.game_exists(game_id):
            return False
        try:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM batting_logs WHERE game_id = ?", (game_id,))
            self._conn.execute("DELETE FROM pitching_logs WHERE game_id = ?", (game_id,))
            self._conn.execute(
                "DELETE FROM milestone_records WHERE game_id = ?", (game_id,)
            )
            self._conn.execute(
                "DELETE FROM streak_processed_games WHERE game_id = ?", (game_id,)
            )
            self._conn.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def reimport_boxscore_file(
        self,
        filepath: str | Path,
        season: int,
        *,
        mlb_only: bool = True,
    ) -> ImportResult:
        """Replace an existing import or import a single box score file."""
        path = Path(filepath)
        game_id = _game_id_from_filename(path.name)
        if game_id < 0:
            return ImportResult(
                game_id=game_id,
                error=f"Invalid filename: {path.name}",
            )
        if not path.is_file():
            return ImportResult(
                game_id=game_id,
                error=f"File not found: {path}",
            )
        if mlb_only and not peek_is_mlb_boxscore(path):
            return ImportResult(game_id=game_id, error="MLB 박스스코어가 아닙니다.")

        if self.game_exists(game_id):
            self.delete_game_import_data(game_id)

        try:
            data = BoxscoreHTMLParser(path).parse()
            return self.import_boxscore(data, season, is_mlb=mlb_only)
        except ParserError as exc:
            return ImportResult(game_id=game_id, error=str(exc))
        except Exception as exc:
            return ImportResult(game_id=game_id, error=str(exc))

    def get_known_game_ids(self) -> set[int]:
        rows = self._conn.execute("SELECT game_id FROM games").fetchall()
        return {int(row["game_id"]) for row in rows}

    def upsert_player(self, player_id: int, short_name: str, full_name: str | None = None) -> None:
        from core.stats.player_display import looks_abbreviated

        new_short = short_name.strip()
        row = self._conn.execute(
            "SELECT full_name, short_name FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        existing_full = str(row["full_name"]).strip() if row else ""
        new_full = self._merge_player_full_name(
            existing_full, new_short, full_name, looks_abbreviated
        )
        self._conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                short_name = excluded.short_name,
                full_name = excluded.full_name
            """,
            (player_id, new_full, new_short),
        )
        from core.roster.player_registry import PlayerRegistry

        PlayerRegistry(self).try_merge_on_import(
            player_id,
            short_name=new_short,
            full_name=new_full,
        )

    @staticmethod
    def _merge_player_full_name(
        existing_full: str,
        short_name: str,
        full_name: str | None,
        looks_abbreviated,
    ) -> str:
        if full_name:
            candidate = full_name.strip()
            if existing_full and looks_abbreviated(candidate):
                if not looks_abbreviated(existing_full):
                    return existing_full
            if len(candidate) >= len(existing_full):
                return candidate
            return existing_full or candidate
        if existing_full and not looks_abbreviated(existing_full):
            return existing_full
        return short_name

    def import_boxscore(
        self, data: BoxscoreData, season: int, *, is_mlb: bool = True
    ) -> ImportResult:
        game_id = data.meta.game_id
        if self.game_exists(game_id):
            return ImportResult(game_id=game_id, skipped=True)

        try:
            self._conn.execute("BEGIN")
            from core.teams.registry import TeamRegistry

            TeamRegistry(self._conn).sync_from_boxscore_meta(
                away_team=data.meta.away_team,
                home_team=data.meta.home_team,
                away_team_id=data.meta.away_team_id,
                home_team_id=data.meta.home_team_id,
            )
            self._insert_game(data, season, is_mlb=is_mlb)
            away_events = assign_batting_events_to_lineup(
                data.away_batting, data.away_batting_notes
            )
            home_events = assign_batting_events_to_lineup(
                data.home_batting, data.home_batting_notes
            )
            away_pitch_events = self._pitching_events_for_team(data.away_pitching_notes)
            home_pitch_events = self._pitching_events_for_team(data.home_pitching_notes)

            for batter in data.away_batting:
                self._insert_batting_log(
                    data,
                    batter,
                    season,
                    away_events.get(batter.player_id, BattingEventCounts()),
                    data.away_batting,
                )
            for batter in data.home_batting:
                self._insert_batting_log(
                    data,
                    batter,
                    season,
                    home_events.get(batter.player_id, BattingEventCounts()),
                    data.home_batting,
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
            batter_ids = [b.player_id for b in data.away_batting + data.home_batting]
            self.update_primary_positions(batter_ids)
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
        mlb_only: bool = True,
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
            try:
                if since_mtime is not None and file_path.stat().st_mtime <= since_mtime:
                    result.skipped_mtime += 1
                    continue

                game_id = _game_id_from_filename(file_path.name)
                if game_id < 0:
                    result.errors.append(
                        ImportResult(
                            game_id=game_id, error=f"Invalid filename: {file_path.name}"
                        )
                    )
                    continue

                if game_id in known_ids:
                    result.skipped_existing += 1
                    continue

                if mlb_only and not peek_is_mlb_boxscore(file_path):
                    result.skipped_non_mlb += 1
                    continue

                result.candidates += 1
                try:
                    data = BoxscoreHTMLParser(file_path).parse()
                    import_result = self.import_boxscore(
                        data, season, is_mlb=mlb_only
                    )
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
            finally:
                if progress_callback:
                    progress_callback(index, len(files), file_path.name)

        if result.imported:
            self.update_primary_positions()
            self._conn.commit()

        return result

    def update_primary_positions(self, player_ids: list[int] | None = None) -> int:
        """Set players.primary_position from most frequent batting_logs.position."""
        if player_ids:
            placeholders = ",".join("?" * len(player_ids))
            id_filter = f"AND bl.player_id IN ({placeholders})"
            params: tuple[Any, ...] = tuple(player_ids)
        else:
            id_filter = ""
            params = ()

        rows = self._conn.execute(
            f"""
            SELECT bl.player_id, bl.position, COUNT(*) AS cnt
            FROM batting_logs bl
            JOIN games g ON g.game_id = bl.game_id AND g.is_mlb = 1
            WHERE bl.position != '' {id_filter}
            GROUP BY bl.player_id, bl.position
            ORDER BY bl.player_id, cnt DESC
            """,
            params,
        ).fetchall()
        best: dict[int, str] = {}
        for row in rows:
            player_id = int(row["player_id"])
            if player_id not in best:
                best[player_id] = str(row["position"])

        updated = 0
        for player_id, position in best.items():
            self._conn.execute(
                "UPDATE players SET primary_position = ? WHERE player_id = ?",
                (position, player_id),
            )
            updated += 1
        return updated

    def _insert_game(
        self, data: BoxscoreData, season: int, *, is_mlb: bool = True
    ) -> None:
        meta = data.meta
        notes = data.game_notes
        self._conn.execute(
            """
            INSERT INTO games (
                game_id, date, season, away_team, home_team,
                away_team_id, home_team_id,
                away_score, home_score, away_innings, home_innings,
                away_hits, home_hits, away_errors, home_errors,
                ballpark, attendance, game_time, weather,
                player_of_game_id, player_of_game_name, special_notes,
                is_mlb
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta.game_id,
                meta.date,
                season,
                meta.away_team,
                meta.home_team,
                meta.away_team_id,
                meta.home_team_id,
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
                1 if is_mlb else 0,
            ),
        )

    def _insert_batting_log(
        self,
        data: BoxscoreData,
        batter: BatterLine,
        season: int,
        events: BattingEventCounts | None = None,
        team_batters: list[BatterLine] | None = None,
    ) -> None:
        self.upsert_player(batter.player_id, batter.player_name)
        note_text = (
            data.away_batting_notes
            if batter.team == data.meta.away_team
            else data.home_batting_notes
        )
        if events is None:
            lineup = team_batters or (
                data.away_batting
                if batter.team == data.meta.away_team
                else data.home_batting
            )
            event_counts = assign_batting_events_to_lineup(lineup, note_text).get(
                batter.player_id, BattingEventCounts()
            )
        else:
            event_counts = events
        lineup = team_batters or (
            data.away_batting
            if batter.team == data.meta.away_team
            else data.home_batting
        )
        is_grand_slam = (
            1
            if batter.player_id
            in grand_slam_player_ids_for_lineup(note_text, lineup)
            else 0
        )
        team_id = batter.team_id
        if team_id is None:
            from core.teams.registry import TeamRegistry

            team_id = TeamRegistry(self._conn).resolve_id(batter.team)
        self._conn.execute(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, team_id, date,
                ab, r, h, rbi, bb, k, lob,
                season_avg, season_hr, season_rbi,
                doubles, triples, home_runs, stolen_bases, hit_by_pitch, gidp,
                position, is_substitute, is_grand_slam
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.meta.game_id,
                batter.player_id,
                season,
                batter.team,
                team_id,
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
                batter.position or "",
                1 if batter.is_substitute else 0,
                is_grand_slam,
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
        is_starter = 1 if team_pitchers and team_pitchers[0].player_id == pitcher.player_id else 0
        special = detect_special_game(
            pitcher, team_pitchers, data.meta, pitcher.team, data
        )
        team_id = pitcher.team_id
        if team_id is None:
            from core.teams.registry import TeamRegistry

            team_id = TeamRegistry(self._conn).resolve_id(pitcher.team)

        self._conn.execute(
            """
            INSERT INTO pitching_logs (
                game_id, player_id, season, team, team_id, date,
                ip_outs, h, r, er, bb, k, hr, bf, pi,
                decision, win, loss, save, season_era,
                game_score, wild_pitch, hit_batsmen,
                is_cg, is_sho, is_no_hitter, is_perfect_game,
                hold, season_holds, is_starter
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.meta.game_id,
                pitcher.player_id,
                season,
                pitcher.team,
                team_id,
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
                1 if pitcher.hold_earned else 0,
                pitcher.season_holds if pitcher.hold_earned else None,
                is_starter,
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
            {_MLB_GAME_JOIN_B}
            JOIN players p ON p.player_id = b.player_id
            WHERE b.season = ? AND b.player_id = ?
            GROUP BY b.player_id
            """,
            (season, player_id),
        ).fetchone()
        if row:
            return dict(row)
        return self._batting_season_from_init(player_id, season)

    def _batting_season_from_init(
        self, player_id: int, season: int
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                cbi.player_id,
                p.short_name,
                p.full_name,
                cbi.g AS games_played,
                cbi.ab,
                cbi.h,
                cbi.r,
                cbi.rbi,
                cbi.bb,
                cbi.k,
                cbi.doubles,
                cbi.triples,
                cbi.hr,
                cbi.sb,
                cbi.hbp
            FROM career_batting_init cbi
            JOIN players p ON p.player_id = cbi.player_id
            WHERE cbi.player_id = ? AND cbi.season = ?
            """,
            (player_id, season),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        ab = int(data.get("ab") or 0)
        h = int(data.get("h") or 0)
        bb = int(data.get("bb") or 0)
        hbp = int(data.get("hbp") or 0)
        pa = ab + bb + hbp
        data["avg"] = round(h / ab, 3) if ab else None
        data["obp"] = round((h + bb) / pa, 3) if pa else None
        data["slg"] = None
        data["ops"] = None
        data["_source"] = "init"
        return data

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
                totals.career_r,
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
            {_MLB_GAME_JOIN_PL}
            JOIN players p ON p.player_id = pl.player_id
            WHERE pl.season = ? AND pl.player_id = ?
            GROUP BY pl.player_id
            """,
            (season, player_id),
        ).fetchone()
        if row:
            data = dict(row)
            data["ip"] = outs_to_ip_float(int(data["ip_outs"]))
            data["ip_display"] = outs_to_ip_str(int(data["ip_outs"]))
            return data
        return self._pitching_season_from_init(player_id, season)

    def _pitching_season_from_init(
        self, player_id: int, season: int
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                cpi.player_id,
                p.short_name,
                p.full_name,
                cpi.g AS games,
                cpi.gs,
                cpi.ip_outs,
                cpi.ha AS h,
                cpi.er,
                cpi.bb,
                cpi.k,
                cpi.hr,
                cpi.w AS wins,
                cpi.l AS losses,
                cpi.s AS saves,
                cpi.cg,
                cpi.sho
            FROM career_pitching_init cpi
            JOIN players p ON p.player_id = cpi.player_id
            WHERE cpi.player_id = ? AND cpi.season = ?
            """,
            (player_id, season),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        ip_outs = int(data.get("ip_outs") or 0)
        er = int(data.get("er") or 0)
        bb = int(data.get("bb") or 0)
        h = int(data.get("h") or 0)
        data["ip"] = outs_to_ip_float(ip_outs)
        data["ip_display"] = outs_to_ip_str(ip_outs)
        data["era"] = round(er * 27 / ip_outs, 2) if ip_outs else None
        data["whip"] = round((bb + h) / (ip_outs / 3.0), 3) if ip_outs else None
        data["_source"] = "init"
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
        extras = self._pitching_career_extras(player_id)
        data["career_g_pit"] = extras["career_g_pit"]
        data["career_gs"] = extras["career_gs"]
        data["career_holds"] = extras["career_holds"]
        return data

    def _pitching_career_extras(self, player_id: int) -> dict[str, float]:
        max_init = self._get_max_init_season()
        init = self._conn.execute(
            """
            SELECT
                COALESCE(SUM(g), 0) AS g,
                COALESCE(SUM(gs), 0) AS gs,
                COALESCE(SUM(holds), 0) AS holds
            FROM career_pitching_init
            WHERE player_id = ? AND season <= ?
            """,
            (player_id, max_init),
        ).fetchone()
        logs = self._conn.execute(
            """
            SELECT
                COUNT(DISTINCT pl.game_id) AS games,
                (
                    SELECT COUNT(*)
                    FROM pitching_logs pl2
                    JOIN (
                        SELECT game_id, team, MIN(id) AS first_id
                        FROM pitching_logs
                        GROUP BY game_id, team
                    ) first_pitcher
                        ON first_pitcher.first_id = pl2.id
                    JOIN games g2 ON g2.game_id = pl2.game_id AND g2.is_mlb = 1
                    WHERE pl2.player_id = ?
                ) AS starts
            FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.player_id = ?
            """,
            (player_id, player_id),
        ).fetchone()
        init_g = float(init["g"]) if init else 0.0
        init_gs = float(init["gs"]) if init else 0.0
        init_holds = float(init["holds"]) if init else 0.0
        log_g = float(logs["games"]) if logs else 0.0
        log_gs = float(logs["starts"]) if logs else 0.0
        holds_row = self._conn.execute(
            """
            SELECT COALESCE(SUM(pl.hold), 0) AS holds
            FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        log_holds = float(holds_row["holds"]) if holds_row else 0.0
        return {
            "career_g_pit": init_g + log_g,
            "career_gs": init_gs + log_gs,
            "career_holds": init_holds + log_holds,
        }

    def was_pitching_starter(self, player_id: int, game_id: int) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM pitching_logs pl
            JOIN (
                SELECT game_id, team, MIN(id) AS first_id
                FROM pitching_logs
                WHERE game_id = ?
                GROUP BY game_id, team
            ) first_pitcher ON first_pitcher.first_id = pl.id
            WHERE pl.player_id = ?
            """,
            (game_id, player_id),
        ).fetchone()
        return row is not None

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
            {_MLB_GAME_JOIN_B}
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
            {_MLB_GAME_JOIN_PL}
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
        if stat == "g":
            row = self._conn.execute(
                """
                SELECT 1 FROM batting_logs bl
                JOIN games g ON g.game_id = bl.game_id AND g.is_mlb = 1
                WHERE bl.player_id = ? AND bl.game_id = ?
                """,
                (player_id, game_id),
            ).fetchone()
            return 1.0 if row else 0.0
        column = _BATTING_GAME_STAT_COLUMNS.get(stat, stat)
        row = self._conn.execute(
            f"SELECT {column} AS value FROM batting_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        return float(row["value"]) if row else 0.0

    def get_game_contribution_pitching(
        self, player_id: int, game_id: int, stat: str
    ) -> float:
        if stat == "g_pit":
            row = self._conn.execute(
                """
                SELECT 1 FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.game_id = ?
                """,
                (player_id, game_id),
            ).fetchone()
            return 1.0 if row else 0.0
        if stat == "gs":
            return 1.0 if self.was_pitching_starter(player_id, game_id) else 0.0
        if stat == "ip_outs":
            row = self._conn.execute(
                "SELECT ip_outs AS value FROM pitching_logs WHERE player_id = ? AND game_id = ?",
                (player_id, game_id),
            ).fetchone()
            return float(row["value"]) if row else 0.0
        column = _PITCHING_GAME_STAT_COLUMNS.get(stat, stat)
        row = self._conn.execute(
            f"SELECT {column} AS value FROM pitching_logs WHERE player_id = ? AND game_id = ?",
            (player_id, game_id),
        ).fetchone()
        return float(row["value"]) if row else 0.0

    def get_batting_season_excluding_game(
        self, player_id: int, season: int, game_id: int
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"""
            SELECT
                SUM(b.ab) AS ab,
                {_batting_ratio_sql()}
            FROM batting_logs b
            {_MLB_GAME_JOIN_B}
            WHERE b.player_id = ? AND b.season = ? AND b.game_id <> ?
            GROUP BY b.player_id
            """,
            (player_id, season, game_id),
        ).fetchone()
        return dict(row) if row else None

    def get_max_prior_season_stat(
        self, player_id: int, season: int, game_id: int, stat: str
    ) -> float | None:
        column = _SEASON_TRACKING_COLUMNS.get(stat)
        if not column:
            return None
        row = self._conn.execute(
            f"""
            SELECT MAX({column}) AS prior_value
            FROM batting_logs b
            JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
            WHERE b.player_id = ? AND b.season = ? AND b.game_id <> ?
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
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.season = ? AND pl.game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        if stat == "season_wins":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(win), 0) AS prior_value
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.season = ? AND pl.game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        if stat == "season_saves":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(save), 0) AS prior_value
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.season = ? AND pl.game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row else 0.0
        if stat == "season_ip":
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(pl.ip_outs), 0) AS prior_outs
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.season = ? AND pl.game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            if not row:
                return 0.0
            from core.stats.ip_utils import outs_to_ip_float

            return outs_to_ip_float(int(row["prior_outs"]))
        if stat == "season_holds":
            row = self._conn.execute(
                """
                SELECT MAX(pl.season_holds) AS prior_value
                FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                WHERE pl.player_id = ? AND pl.season = ? AND pl.game_id <> ?
                """,
                (player_id, season, game_id),
            ).fetchone()
            return float(row["prior_value"]) if row and row["prior_value"] is not None else 0.0
        return 0.0

    def _get_max_init_season(self) -> int:
        from core.db.meta import get_init_season_coverage

        return get_init_season_coverage(self._conn)

    def get_db_summary(self) -> dict[str, int]:
        games = self._conn.execute(
            "SELECT COUNT(*) FROM games WHERE is_mlb = 1"
        ).fetchone()[0]
        players = self._conn.execute(
            """
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT b.player_id FROM batting_logs b
                JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                UNION
                SELECT pl.player_id FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            )
            """
        ).fetchone()[0]
        return {"games": int(games), "players": int(players)}

    def get_available_seasons(self) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT season FROM (
                SELECT b.season FROM batting_logs b
                JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                UNION
                SELECT pl.season FROM pitching_logs pl
                JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                UNION
                SELECT season FROM career_batting_init
                UNION
                SELECT season FROM career_pitching_init
            )
            ORDER BY season DESC
            """
        ).fetchall()
        return [int(row[0]) for row in rows]

    def get_tracked_players(
        self,
        tracked_teams: list[str] | None = None,
        *,
        custom_teams: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        tokens = [team.strip().upper() for team in (tracked_teams or []) if team.strip()]
        if not tokens:
            rows = self._conn.execute(
                """
                SELECT
                    p.player_id,
                    p.full_name,
                    p.short_name,
                    COALESCE(p.primary_position, '') AS primary_position,
                    EXISTS(
                        SELECT 1 FROM batting_logs b
                        JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                        WHERE b.player_id = p.player_id
                    ) AS is_batter,
                    EXISTS(
                        SELECT 1 FROM pitching_logs pl
                        JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                        WHERE pl.player_id = p.player_id
                    ) AS is_pitcher
                FROM players p
                WHERE p.player_id IN (
                    SELECT b.player_id FROM batting_logs b
                    JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                    UNION
                    SELECT pl.player_id FROM pitching_logs pl
                    JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                    UNION
                    SELECT player_id FROM player_roster
                    UNION
                    SELECT player_id FROM career_batting_init
                    UNION
                    SELECT player_id FROM career_pitching_init
                )
                ORDER BY p.full_name
                """
            ).fetchall()
        else:
            names = expand_tracked_teams(tokens, custom_teams)
            placeholders = ",".join("?" * len(names))
            roster_where, roster_params = build_tracked_team_match_sql(
                tokens, custom_teams
            )
            affiliation_where, affiliation_params = build_tracked_team_match_sql(
                tokens,
                custom_teams,
                abbr_col="pta.team_abbr",
                name_col="pta.team_name",
            )
            rows = self._conn.execute(
                f"""
                SELECT DISTINCT
                    p.player_id,
                    p.full_name,
                    p.short_name,
                    COALESCE(p.primary_position, '') AS primary_position,
                    EXISTS(
                        SELECT 1 FROM batting_logs b2
                        JOIN games g2 ON g2.game_id = b2.game_id AND g2.is_mlb = 1
                        WHERE b2.player_id = p.player_id
                    ) AS is_batter,
                    EXISTS(
                        SELECT 1 FROM pitching_logs pl2
                        JOIN games g2 ON g2.game_id = pl2.game_id AND g2.is_mlb = 1
                        WHERE pl2.player_id = p.player_id
                    ) AS is_pitcher
                FROM players p
                WHERE p.player_id IN (
                    SELECT b.player_id FROM batting_logs b
                    JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                    WHERE b.team IN ({placeholders})
                    UNION
                    SELECT pl.player_id FROM pitching_logs pl
                    JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                    WHERE pl.team IN ({placeholders})
                    UNION
                    SELECT player_id FROM player_roster
                    WHERE {roster_where}
                    UNION
                    SELECT DISTINCT pta.player_id
                    FROM player_team_affiliations pta
                    WHERE {affiliation_where}
                )
                ORDER BY p.full_name
                """,
                names + names + roster_params + affiliation_params,
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_player_roster(
        self, entries: list[dict[str, Any]], *, season: int
    ) -> int:
        if not entries:
            return 0
        self._conn.executemany(
            """
            INSERT INTO player_roster (player_id, season, team_abbr, team_name, team_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(player_id, season) DO UPDATE SET
                team_abbr = excluded.team_abbr,
                team_name = excluded.team_name,
                team_id = COALESCE(excluded.team_id, player_roster.team_id)
            """,
            [
                (
                    int(entry["player_id"]),
                    season,
                    str(entry.get("team_abbr") or "").strip(),
                    str(entry.get("team_name") or "").strip(),
                    entry.get("team_id"),
                )
                for entry in entries
                if entry.get("team_abbr")
            ],
        )
        self._conn.commit()
        return len(entries)

    def upsert_player_team_affiliations(
        self, entries: list[dict[str, Any]]
    ) -> int:
        if not entries:
            return 0
        self._conn.executemany(
            """
            INSERT INTO player_team_affiliations (
                player_id, season, team_abbr, team_name
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(player_id, season, team_abbr) DO UPDATE SET
                team_name = excluded.team_name
            """,
            [
                (
                    int(entry["player_id"]),
                    int(entry["season"]),
                    str(entry.get("team_abbr") or "").strip().upper(),
                    str(entry.get("team_name") or "").strip(),
                )
                for entry in entries
                if entry.get("team_abbr")
            ],
        )
        self._conn.commit()
        return len(entries)

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
            JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
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
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
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
            """
            SELECT COUNT(DISTINCT pl.game_id) FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.player_id = ?
            """,
            (player_id,),
        ).fetchone()[0]
        log_cg = self._conn.execute(
            """
            SELECT COALESCE(SUM(pl.is_cg),0) FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.player_id = ?
            """,
            (player_id,),
        ).fetchone()[0]
        log_sho = self._conn.execute(
            """
            SELECT COALESCE(SUM(pl.is_sho),0) FROM pitching_logs pl
            JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
            WHERE pl.player_id = ?
            """,
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

    def get_player_ids_for_games(self, game_ids: list[int]) -> set[int]:
        if not game_ids:
            return set()
        placeholders = ",".join("?" * len(game_ids))
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT player_id FROM (
                SELECT player_id FROM batting_logs WHERE game_id IN ({placeholders})
                UNION
                SELECT player_id FROM pitching_logs WHERE game_id IN ({placeholders})
            )
            """,
            game_ids + game_ids,
        ).fetchall()
        return {int(row[0]) for row in rows}

    def count_milestone_predictions(self, season: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM milestone_predictions WHERE season = ?",
            (season,),
        ).fetchone()
        return int(row[0])

    def clear_milestone_predictions(self, season: int) -> None:
        self._conn.execute(
            "DELETE FROM milestone_predictions WHERE season = ?",
            (season,),
        )
        self._conn.commit()

    def delete_milestone_predictions(
        self, season: int, keys: list[tuple[int, str]]
    ) -> None:
        if not keys:
            return
        self._conn.executemany(
            """
            DELETE FROM milestone_predictions
            WHERE season = ? AND player_id = ? AND milestone_key = ?
            """,
            [(season, player_id, milestone_key) for player_id, milestone_key in keys],
        )
        self._conn.commit()

    def upsert_milestone_predictions(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT INTO milestone_predictions (
                player_id, milestone_key, season, player_name, milestone_label,
                grade, current_value, threshold, remaining, progress_pct, season_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, milestone_key, season) DO UPDATE SET
                player_name = excluded.player_name,
                milestone_label = excluded.milestone_label,
                grade = excluded.grade,
                current_value = excluded.current_value,
                threshold = excluded.threshold,
                remaining = excluded.remaining,
                progress_pct = excluded.progress_pct,
                season_note = excluded.season_note,
                updated_at = datetime('now')
            """,
            [
                (
                    row["player_id"],
                    row["milestone_key"],
                    row["season"],
                    row["player_name"],
                    row["milestone_label"],
                    row["grade"],
                    row["current_value"],
                    row["threshold"],
                    row["remaining"],
                    row["progress_pct"],
                    row["season_note"],
                )
                for row in rows
            ],
        )
        self._conn.commit()

    def get_milestone_predictions(
        self,
        season: int,
        *,
        player_id: int | None = None,
        tracked_teams: list[str] | None = None,
        custom_teams: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                mp.player_id,
                mp.milestone_key,
                mp.season,
                mp.player_name,
                mp.milestone_label,
                mp.grade,
                mp.current_value,
                mp.threshold,
                mp.remaining,
                mp.progress_pct,
                mp.season_note,
                mp.updated_at
            FROM milestone_predictions mp
            WHERE mp.season = ?
        """
        params: list[Any] = [season]
        if player_id is not None:
            query += " AND mp.player_id = ?"
            params.append(player_id)
        if tracked_teams:
            tokens = [team.strip().upper() for team in tracked_teams if team.strip()]
            names = expand_tracked_teams(tokens, custom_teams)
            name_ph = ",".join("?" * len(names))
            token_ph = ",".join("?" * len(tokens))
            query += f"""
                AND mp.player_id IN (
                    SELECT b.player_id FROM batting_logs b
                    JOIN games g ON g.game_id = b.game_id AND g.is_mlb = 1
                    WHERE b.team IN ({name_ph})
                    UNION
                    SELECT pl.player_id FROM pitching_logs pl
                    JOIN games g ON g.game_id = pl.game_id AND g.is_mlb = 1
                    WHERE pl.team IN ({name_ph})
                    UNION
                    SELECT player_id FROM player_roster
                    WHERE team_abbr IN ({token_ph}) OR team_name IN ({name_ph})
                )
            """
            params.extend(names + names + tokens + names)
        query += " ORDER BY mp.progress_pct DESC, mp.player_name"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_recent_milestone_records(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mr.id,
                   CASE
                       WHEN mr.player_id = 0 AND mr.team IS NOT NULL AND mr.team != ''
                           THEN mr.team
                       ELSE COALESCE(p.short_name, p.full_name, '')
                   END AS display_name,
                   mr.player_id,
                   mr.milestone_key,
                   mr.milestone_label,
                   mr.scope,
                   mr.game_id,
                   mr.achieved_date,
                   mr.achieved_value,
                   mr.season,
                   mr.notes,
                   mr.team,
                   mr.recorded_at
            FROM milestone_records mr
            LEFT JOIN players p ON p.player_id = mr.player_id
            ORDER BY mr.recorded_at DESC, mr.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_all_milestone_records_export(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mr.*,
                   COALESCE(p.full_name, p.short_name, '') AS player_name
            FROM milestone_records mr
            LEFT JOIN players p ON p.player_id = mr.player_id
            ORDER BY mr.recorded_at, mr.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_player_milestone_records(self, player_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mr.*
            FROM milestone_records mr
            WHERE mr.player_id = ?
              AND (mr.team IS NULL OR mr.team = '')
            ORDER BY mr.achieved_date DESC, mr.id DESC
            """,
            (player_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_milestone_record_by_id(self, record_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT mr.*,
                   CASE
                       WHEN mr.player_id = 0 AND mr.team IS NOT NULL AND mr.team != ''
                           THEN mr.team
                       ELSE COALESCE(p.short_name, p.full_name, '')
                   END AS player_name
            FROM milestone_records mr
            LEFT JOIN players p ON p.player_id = mr.player_id
            WHERE mr.id = ?
            """,
            (record_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_milestone_record(
        self,
        record_id: int,
        *,
        achieved_date: str,
        achieved_value: float,
        season: int | None,
        games_at_achievement: int | None,
        opponent_team: str | None,
        opponent_player: str | None,
        description: str | None,
        notes: str | None,
    ) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE milestone_records
            SET achieved_date = ?,
                achieved_value = ?,
                season = ?,
                games_at_achievement = ?,
                opponent_team = ?,
                opponent_player = ?,
                description = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                achieved_date,
                achieved_value,
                season,
                games_at_achievement,
                opponent_team or None,
                opponent_player or None,
                description or None,
                notes or None,
                record_id,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_milestone_record(self, record_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM milestone_records WHERE id = ?",
            (record_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0


_BATTING_GAME_STAT_COLUMNS = {
    "h": "h",
    "hr": "home_runs",
    "rbi": "rbi",
    "r": "r",
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
    "hold": "hold",
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
                bl.player_id,
                COUNT(DISTINCT bl.game_id) AS g,
                SUM(bl.ab), SUM(bl.h), SUM(bl.doubles), SUM(bl.triples), SUM(bl.home_runs),
                SUM(bl.rbi), SUM(bl.r), SUM(bl.stolen_bases), SUM(bl.bb), SUM(bl.k)
            FROM batting_logs bl
            JOIN games gm ON gm.game_id = bl.game_id AND gm.is_mlb = 1
            GROUP BY bl.player_id
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
                pl.player_id,
                SUM(pl.ip_outs), SUM(pl.win), SUM(pl.loss), SUM(pl.save), SUM(pl.k),
                SUM(pl.er), SUM(pl.h), SUM(pl.bb), SUM(pl.hr)
            FROM pitching_logs pl
            JOIN games gm ON gm.game_id = pl.game_id AND gm.is_mlb = 1
            GROUP BY pl.player_id
        )
        GROUP BY player_id
    """


def _game_id_from_filename(filename: str) -> int:
    import re

    match = re.search(r"game_box_(\d+)\.html", filename, re.I)
    return int(match.group(1)) if match else -1
