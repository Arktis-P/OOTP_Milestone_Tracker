"""Import pre-tracker career stats from OOTP player stats text exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.db.meta import get_init_season_coverage, touch_import_meta
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import ip_to_outs

ImportMode = Literal["first_time", "refresh", "mid_season"]
SeasonFilter = Literal["lt", "eq", "gap", "all"]

BATTING_COLS = [
    "player_id",
    "lastname",
    "firstname",
    "season",
    "team_id",
    "g",
    "gs",
    "pa",
    "ab",
    "h",
    "doubles",
    "triples",
    "hr",
    "rbi",
    "r",
    "sb",
    "cs",
    "bb",
    "hbp",
    "k",
    "sh",
    "sf",
    "gdp",
    "ibb",
    "ci",
    "pitches_seen",
    "vorp",
    "split_id",
    "team_abbr",
    "league_abbr",
    "team_name",
    "league_name",
    "league_level_id",
    "bbrefid",
    "bbrefminorid",
    "ootp_pid",
    "eol",
]

PITCHING_COLS = [
    "player_id",
    "lastname",
    "firstname",
    "season",
    "team_id",
    "g",
    "gs",
    "w",
    "l",
    "s",
    "ip",
    "ha",
    "r",
    "er",
    "bb",
    "hbp",
    "k",
    "bf",
    "ab",
    "singles",
    "doubles",
    "triples",
    "hr",
    "tb",
    "sh",
    "sf",
    "ci",
    "iw",
    "bk",
    "wp",
    "dp",
    "qs",
    "svopp",
    "blownsv",
    "reliefapp",
    "cg",
    "sho",
    "holds",
    "sb",
    "cs",
    "gb",
    "fb",
    "pitches",
    "runsupport",
    "war",
    "babip",
    "split_id",
    "team_abbr",
    "league_abbr",
    "team_name",
    "league_name",
    "league_level_id",
    "bbrefid",
    "bbrefminorid",
    "ootp_pid",
    "eol",
]

BATTING_SUM_FIELDS = [
    "g",
    "pa",
    "ab",
    "h",
    "doubles",
    "triples",
    "hr",
    "rbi",
    "r",
    "sb",
    "cs",
    "bb",
    "hbp",
    "k",
    "sh",
    "sf",
    "gdp",
]

PITCHING_SUM_FIELDS = [
    "g",
    "gs",
    "w",
    "l",
    "s",
    "ip_outs",
    "ha",
    "r",
    "er",
    "bb",
    "hbp",
    "k",
    "hr",
    "cg",
    "sho",
    "wp",
    "bk",
    "holds",
]

BATTING_COMPARE_STATS = ["h", "hr", "rbi", "sb", "bb", "k", "doubles", "triples", "ab"]
PITCHING_COMPARE_STATS = ["w", "l", "s", "k", "er", "bb", "hr", "ha"]


@dataclass
class StatDiff:
    player_id: int
    player_name: str
    stat: str
    db_value: int | float
    file_value: int | float
    season: int

    @property
    def diff(self) -> float:
        return float(self.file_value) - float(self.db_value)


@dataclass
class InitImportResult:
    mode: str
    kind: str = "batting"
    inserted: int = 0
    replaced: int = 0
    skipped: int = 0
    diffs: list[StatDiff] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_scanned: int = 0
    pending_rows: dict[tuple[int, int], dict[str, Any]] = field(default_factory=dict)
    saved: bool = False


class InitialImporter:
    """Parse OOTP player_batting_stats / player_pitching_stats exports."""

    def __init__(self, aggregator: Aggregator) -> None:
        self.aggregator = aggregator

    def import_batting(
        self,
        filepath: str | Path,
        mode: ImportMode,
        current_season: int,
        *,
        persist: bool = True,
    ) -> InitImportResult:
        return self._import_kind(
            filepath, kind="batting", mode=mode, current_season=current_season, persist=persist
        )

    def import_pitching(
        self,
        filepath: str | Path,
        mode: ImportMode,
        current_season: int,
        *,
        persist: bool = True,
    ) -> InitImportResult:
        return self._import_kind(
            filepath, kind="pitching", mode=mode, current_season=current_season, persist=persist
        )

    def import_all(
        self,
        batting_path: str | Path | None,
        pitching_path: str | Path | None,
        mode: ImportMode,
        current_season: int,
        *,
        persist: bool = True,
    ) -> tuple[InitImportResult | None, InitImportResult | None]:
        batting_result = None
        pitching_result = None
        if batting_path:
            batting_result = self.import_batting(
                batting_path, mode, current_season, persist=persist
            )
        if pitching_path:
            pitching_result = self.import_pitching(
                pitching_path, mode, current_season, persist=persist
            )
        return batting_result, pitching_result

    def persist_pending(self, result: InitImportResult, *, replace: bool) -> InitImportResult:
        if not result.pending_rows:
            return result
        conn = self.aggregator.conn
        try:
            conn.execute("BEGIN")
            if result.kind == "batting":
                inserted, replaced = self._persist_batting_rows(
                    result.pending_rows, replace=replace
                )
            else:
                inserted, replaced = self._persist_pitching_rows(
                    result.pending_rows, replace=replace
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            result.errors.append(str(exc))
            return result

        result.inserted = inserted
        result.replaced = replaced
        result.saved = True
        return result

    def get_init_summary(self) -> dict[str, Any]:
        from core.db.meta import get_meta

        conn = self.aggregator.conn
        batting = conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM career_batting_init"
        ).fetchone()
        pitching = conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM career_pitching_init"
        ).fetchone()
        coverage = get_init_season_coverage(conn)
        return {
            "batting_players": int(batting[0] if batting else 0),
            "pitching_players": int(pitching[0] if pitching else 0),
            "season_coverage": coverage,
            "batting_imported_at": get_meta(conn, "init_batting_imported_at", ""),
            "pitching_imported_at": get_meta(conn, "init_pitching_imported_at", ""),
            "last_refreshed_at": get_meta(conn, "init_last_refreshed_at", ""),
        }

    def is_init_empty(self, kind: str = "batting") -> bool:
        table = "career_batting_init" if kind == "batting" else "career_pitching_init"
        row = self.aggregator.conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
        return int(row["cnt"]) == 0

    def _import_kind(
        self,
        filepath: str | Path,
        *,
        kind: str,
        mode: ImportMode,
        current_season: int,
        persist: bool,
    ) -> InitImportResult:
        path = Path(filepath)
        result = InitImportResult(mode=mode, kind=kind)
        if not path.is_file():
            result.errors.append(f"File not found: {path}")
            return result

        col_names = BATTING_COLS if kind == "batting" else PITCHING_COLS
        try:
            rows = self._parse_file(path, col_names)
        except Exception as exc:
            result.errors.append(str(exc))
            return result

        result.total_scanned = len(rows)
        coverage = get_init_season_coverage(self.aggregator.conn)

        if mode == "first_time":
            aggregated = self._filter_and_aggregate(
                rows, season_filter="lt", current_season=current_season
            )
            result.pending_rows = aggregated
            if persist and aggregated:
                inserted, _ = self._save_rows(kind, aggregated, replace=False)
                result.inserted = inserted
                result.saved = True
                touch_import_meta(
                    self.aggregator.conn,
                    kind,
                    max(current_season - 1, 0),
                )
                self.aggregator.conn.commit()

        elif mode == "refresh":
            last_season = current_season - 1
            aggregated = self._filter_and_aggregate(
                rows, season_filter="eq", current_season=current_season, target_season=last_season
            )
            result.pending_rows = aggregated
            if kind == "batting":
                result.diffs = self._compare_batting(aggregated, last_season)
            else:
                result.diffs = self._compare_pitching(aggregated, last_season)
            if persist and aggregated:
                _, replaced = self._save_rows(kind, aggregated, replace=True)
                result.replaced = replaced
                result.saved = True
                touch_import_meta(self.aggregator.conn, kind, last_season)
                self.aggregator.conn.commit()

        elif mode == "mid_season":
            current_rows = self._filter_and_aggregate(
                rows, season_filter="eq", current_season=current_season, target_season=current_season
            )
            if kind == "batting":
                result.diffs.extend(self._compare_batting(current_rows, current_season))
            else:
                result.diffs.extend(self._compare_pitching(current_rows, current_season))

            if coverage < current_season - 1:
                gap_rows = self._filter_and_aggregate(
                    rows,
                    season_filter="gap",
                    current_season=current_season,
                    coverage_season=coverage,
                )
                if gap_rows:
                    result.pending_rows = gap_rows
                    for season in {key[1] for key in gap_rows}:
                        if kind == "batting":
                            season_rows = {k: v for k, v in gap_rows.items() if k[1] == season}
                            result.diffs.extend(self._compare_batting(season_rows, season))
                        else:
                            season_rows = {k: v for k, v in gap_rows.items() if k[1] == season}
                            result.diffs.extend(self._compare_pitching(season_rows, season))
                    if persist:
                        _, replaced = self._save_rows(kind, gap_rows, replace=True)
                        result.replaced = replaced
                        result.saved = True
                        touch_import_meta(
                            self.aggregator.conn,
                            kind,
                            max(current_season - 1, coverage),
                        )
                        self.aggregator.conn.commit()

        return result

    def _parse_file(self, filepath: Path, col_names: list[str]) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(_read_export_lines(filepath), start=1):
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue
            fields = [part.strip() for part in line.split(",")]
            if len(fields) < len(col_names) - 5:
                raise ValueError(f"line {line_no}: not enough columns ({len(fields)})")
            row = {}
            for idx, name in enumerate(col_names):
                if idx >= len(fields):
                    row[name] = ""
                else:
                    row[name] = fields[idx]
            row["player_id"] = _int(row["player_id"])
            row["season"] = _int(row["season"])
            row["split_id"] = _int(row["split_id"])
            row["league_level_id"] = _int(row["league_level_id"])
            if row.get("ip"):
                row["ip_outs"] = ip_to_outs(str(row["ip"]))
            parsed.append(row)
        return parsed

    def _filter_and_aggregate(
        self,
        rows: list[dict[str, Any]],
        *,
        season_filter: SeasonFilter,
        current_season: int,
        target_season: int | None = None,
        coverage_season: int = 0,
    ) -> dict[tuple[int, int], dict[str, Any]]:
        totals: dict[tuple[int, int], dict[str, Any]] = {}
        if rows and "ip" in rows[0]:
            sum_fields = PITCHING_SUM_FIELDS
        else:
            sum_fields = BATTING_SUM_FIELDS

        for row in rows:
            if row["league_level_id"] != 1 or row["split_id"] != 1:
                continue
            season = int(row["season"])
            if not self._season_matches(
                season,
                season_filter,
                current_season=current_season,
                target_season=target_season,
                coverage_season=coverage_season,
            ):
                continue

            key = (int(row["player_id"]), season)
            if key not in totals:
                totals[key] = {
                    "player_id": key[0],
                    "season": season,
                    "firstname": row["firstname"],
                    "lastname": row["lastname"],
                }
                for name in sum_fields:
                    totals[key][name] = 0

            bucket = totals[key]
            for name in sum_fields:
                if name == "ip_outs":
                    bucket[name] += int(row.get("ip_outs") or 0)
                else:
                    bucket[name] += _int(row.get(name, 0))

        return totals

    @staticmethod
    def _season_matches(
        season: int,
        season_filter: SeasonFilter,
        *,
        current_season: int,
        target_season: int | None,
        coverage_season: int,
    ) -> bool:
        if season_filter == "lt":
            return season < current_season
        if season_filter == "eq":
            return season == (target_season if target_season is not None else current_season)
        if season_filter == "gap":
            return coverage_season < season < current_season
        return True

    def _compare_batting(
        self, aggregated: dict[tuple[int, int], dict[str, Any]], season: int
    ) -> list[StatDiff]:
        diffs: list[StatDiff] = []
        for (player_id, row_season), row in aggregated.items():
            if row_season != season:
                continue
            db_stats = self.aggregator.get_batting_season(player_id, season) or {}
            player_name = self._player_name(player_id, row)
            for stat in BATTING_COMPARE_STATS:
                db_val = int(db_stats.get(stat if stat != "doubles" else "doubles", 0) or 0)
                file_val = int(row.get(stat, 0) or 0)
                if db_val != file_val:
                    diffs.append(
                        StatDiff(player_id, player_name, stat, db_val, file_val, season)
                    )
        return diffs

    def _compare_pitching(
        self, aggregated: dict[tuple[int, int], dict[str, Any]], season: int
    ) -> list[StatDiff]:
        diffs: list[StatDiff] = []
        for (player_id, row_season), row in aggregated.items():
            if row_season != season:
                continue
            db_stats = self.aggregator.get_pitching_season(player_id, season) or {}
            player_name = self._player_name(player_id, row)
            stat_map = {"w": "wins", "l": "losses", "s": "saves", "ha": "h"}
            for stat in PITCHING_COMPARE_STATS:
                db_key = stat_map.get(stat, stat)
                db_val = int(db_stats.get(db_key, 0) or 0)
                file_val = int(row.get(stat, 0) or 0)
                if db_val != file_val:
                    diffs.append(
                        StatDiff(player_id, player_name, stat, db_val, file_val, season)
                    )
        return diffs

    def _player_name(self, player_id: int, row: dict[str, Any]) -> str:
        full_name = f"{row.get('firstname', '')} {row.get('lastname', '')}".strip()
        short = f"{row.get('firstname', '')[:1]}. {row.get('lastname', '')}".strip()
        self.aggregator.upsert_player(player_id, short, full_name)
        existing = self.aggregator.conn.execute(
            "SELECT COALESCE(short_name, full_name) AS name FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return str(existing["name"]) if existing else full_name or str(player_id)

    def _save_rows(
        self, kind: str, rows: dict[tuple[int, int], dict[str, Any]], *, replace: bool
    ) -> tuple[int, int]:
        conn = self.aggregator.conn
        conn.execute("BEGIN")
        try:
            if kind == "batting":
                inserted, replaced = self._persist_batting_rows(rows, replace=replace)
            else:
                inserted, replaced = self._persist_pitching_rows(rows, replace=replace)
            conn.commit()
            return inserted, replaced
        except Exception:
            conn.rollback()
            raise

    def _persist_batting_rows(
        self, rows: dict[tuple[int, int], dict[str, Any]], *, replace: bool
    ) -> tuple[int, int]:
        inserted = replaced = 0
        sql_ignore = """
            INSERT OR IGNORE INTO career_batting_init (
                player_id, season, g, pa, ab, h, doubles, triples, hr, rbi,
                r, sb, cs, bb, hbp, k, sh, sf, gdp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        sql_replace = """
            INSERT INTO career_batting_init (
                player_id, season, g, pa, ab, h, doubles, triples, hr, rbi,
                r, sb, cs, bb, hbp, k, sh, sf, gdp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, season) DO UPDATE SET
                g=excluded.g, pa=excluded.pa, ab=excluded.ab, h=excluded.h,
                doubles=excluded.doubles, triples=excluded.triples, hr=excluded.hr,
                rbi=excluded.rbi, r=excluded.r, sb=excluded.sb, cs=excluded.cs,
                bb=excluded.bb, hbp=excluded.hbp, k=excluded.k, sh=excluded.sh,
                sf=excluded.sf, gdp=excluded.gdp
        """
        for row in rows.values():
            self._player_name(int(row["player_id"]), row)
            values = (
                int(row["player_id"]),
                int(row["season"]),
                int(row.get("g", 0)),
                int(row.get("pa", 0)),
                int(row.get("ab", 0)),
                int(row.get("h", 0)),
                int(row.get("doubles", 0)),
                int(row.get("triples", 0)),
                int(row.get("hr", 0)),
                int(row.get("rbi", 0)),
                int(row.get("r", 0)),
                int(row.get("sb", 0)),
                int(row.get("cs", 0)),
                int(row.get("bb", 0)),
                int(row.get("hbp", 0)),
                int(row.get("k", 0)),
                int(row.get("sh", 0)),
                int(row.get("sf", 0)),
                int(row.get("gdp", 0)),
            )
            if replace:
                self.aggregator.conn.execute(sql_replace, values)
                replaced += 1
            else:
                cur = self.aggregator.conn.execute(sql_ignore, values)
                if cur.rowcount:
                    inserted += 1
        return inserted, replaced

    def _persist_pitching_rows(
        self, rows: dict[tuple[int, int], dict[str, Any]], *, replace: bool
    ) -> tuple[int, int]:
        inserted = replaced = 0
        sql_ignore = """
            INSERT OR IGNORE INTO career_pitching_init (
                player_id, season, g, gs, w, l, s, ip_outs,
                ha, r, er, bb, hbp, k, hr, cg, sho, wp, bk, holds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        sql_replace = """
            INSERT INTO career_pitching_init (
                player_id, season, g, gs, w, l, s, ip_outs,
                ha, r, er, bb, hbp, k, hr, cg, sho, wp, bk, holds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, season) DO UPDATE SET
                g=excluded.g, gs=excluded.gs, w=excluded.w, l=excluded.l,
                s=excluded.s, ip_outs=excluded.ip_outs, ha=excluded.ha,
                r=excluded.r, er=excluded.er, bb=excluded.bb, hbp=excluded.hbp,
                k=excluded.k, hr=excluded.hr, cg=excluded.cg, sho=excluded.sho,
                wp=excluded.wp, bk=excluded.bk, holds=excluded.holds
        """
        for row in rows.values():
            self._player_name(int(row["player_id"]), row)
            values = (
                int(row["player_id"]),
                int(row["season"]),
                int(row.get("g", 0)),
                int(row.get("gs", 0)),
                int(row.get("w", 0)),
                int(row.get("l", 0)),
                int(row.get("s", 0)),
                int(row.get("ip_outs", 0)),
                int(row.get("ha", 0)),
                int(row.get("r", 0)),
                int(row.get("er", 0)),
                int(row.get("bb", 0)),
                int(row.get("hbp", 0)),
                int(row.get("k", 0)),
                int(row.get("hr", 0)),
                int(row.get("cg", 0)),
                int(row.get("sho", 0)),
                int(row.get("wp", 0)),
                int(row.get("bk", 0)),
                int(row.get("holds", 0)),
            )
            if replace:
                self.aggregator.conn.execute(sql_replace, values)
                replaced += 1
            else:
                cur = self.aggregator.conn.execute(sql_ignore, values)
                if cur.rowcount:
                    inserted += 1
        return inserted, replaced


def _read_export_lines(filepath: Path) -> list[str]:
    """Read OOTP stats export text (UTF-8 or UTF-16)."""
    raw = filepath.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    elif b"\x00" in raw[: min(len(raw), 200)]:
        text = raw.decode("utf-16-le")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.splitlines()


def _int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip().strip('"')
    if not text:
        return 0
    return int(float(text))
