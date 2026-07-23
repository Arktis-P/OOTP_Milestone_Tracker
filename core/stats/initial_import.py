"""Import pre-tracker career stats from OOTP player stats text exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.db.meta import get_init_season_coverage, touch_import_meta
from core.db.sqlite_config import commit_if_in_transaction
from core.i18n import tr
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import ip_to_outs, outs_to_ip_float
from core.stats.team_filter import (
    discover_mlb_teams_from_rows,
    find_unknown_mlb_teams,
    is_ootp_mlb_league_row,
)

ImportMode = Literal["first_time", "refresh", "mid_season"]
SeasonFilter = Literal["lt", "eq", "gap", "all"]

# Standard OOTP export file names inside a stats snapshot directory.
SNAPSHOT_BATTING_FILENAME = "player_batting_stats.txt"
SNAPSHOT_PITCHING_FILENAME = "player_pitching_stats.txt"

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
BATTING_SNAPSHOT_VALIDATE_STATS = [
    "ab",
    "h",
    "r",
    "rbi",
    "bb",
    "hbp",
    "k",
    "hr",
    "sb",
    "doubles",
    "triples",
]
PITCHING_SNAPSHOT_VALIDATE_STATS = [
    "ip_outs",
    "h",
    "er",
    "bb",
    "k",
    "hr",
    "w",
    "l",
    "sv",
    "gs",
    "holds",
]


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


class ExportSnapshotError(RuntimeError):
    """An OOTP export could not be turned into a read-only season snapshot."""


class ExportFileMissingError(ExportSnapshotError):
    """No export file was supplied, or the supplied path does not exist."""


class ExportFileEmptyError(ExportSnapshotError):
    """The export file exists but carries no stat rows at all."""


class ExportParseError(ExportSnapshotError):
    """The export file exists but its contents could not be parsed."""


@dataclass(frozen=True)
class SeasonExportSnapshot:
    """Read-only season totals parsed straight from OOTP export files.

    The rows carry the same keys as
    ``Aggregator.get_season_batting_totals`` / ``get_season_pitching_totals`` so
    they can be handed to ``MilestoneChecker.check_season_ratios`` as an
    override. Building a snapshot never writes to the database, so it cannot
    contaminate career init tables or double-add box score data.
    """

    season: int
    batting: tuple[dict[str, Any], ...] = ()
    pitching: tuple[dict[str, Any], ...] = ()
    sources: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.batting and not self.pitching

    def as_totals_override(self) -> dict[str, list[dict[str, Any]]]:
        """Override map for the checker — only categories actually exported.

        A category that was read stays in the map even when it produced no
        rows, so the checker judges "no qualified players" instead of quietly
        falling back to box-score totals the export was meant to correct.
        """
        override: dict[str, list[dict[str, Any]]] = {}
        if "batting" in self.kinds:
            override["batting"] = list(self.batting)
        if "pitching" in self.kinds:
            override["pitching"] = list(self.pitching)
        return override


SnapshotValidationStatus = Literal["complete", "no_current_season", "incomplete"]


@dataclass(frozen=True)
class SeasonSnapshotValidationIssue:
    category: str
    player_id: int
    player_name: str
    stat: str
    export_value: int
    db_value: int


@dataclass(frozen=True)
class SeasonSnapshotValidationResult:
    status: SnapshotValidationStatus
    issues: tuple[SeasonSnapshotValidationIssue, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"


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
        self._korean_name_store_cache = None

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
        commit_if_in_transaction(conn)
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

    def validate_season_snapshot(
        self, snapshot: SeasonExportSnapshot
    ) -> SeasonSnapshotValidationResult:
        """Check that export season rows are at least as complete as DB boxscores.

        This is intentionally read-only. Export totals may be greater than DB
        totals because a season-final export can include games the local
        boxscore database has not imported yet.
        """
        if not snapshot.batting and not snapshot.pitching:
            return SeasonSnapshotValidationResult(status="no_current_season")
        if {"batting", "pitching"} <= set(snapshot.kinds) and (
            not snapshot.batting or not snapshot.pitching
        ):
            return SeasonSnapshotValidationResult(status="no_current_season")

        batting_issues = self._validate_snapshot_category(
            "batting",
            snapshot.batting,
            self.aggregator.get_season_batting_totals(snapshot.season),
            BATTING_SNAPSHOT_VALIDATE_STATS,
        )
        pitching_issues = self._validate_snapshot_category(
            "pitching",
            snapshot.pitching,
            self.aggregator.get_season_pitching_totals(snapshot.season),
            PITCHING_SNAPSHOT_VALIDATE_STATS,
        )
        issues = (*batting_issues, *pitching_issues)
        return SeasonSnapshotValidationResult(
            status="incomplete" if issues else "complete",
            issues=issues,
        )

    def _validate_snapshot_category(
        self,
        category: str,
        export_rows: tuple[dict[str, Any], ...],
        db_rows: list[dict[str, Any]],
        stats: list[str],
    ) -> tuple[SeasonSnapshotValidationIssue, ...]:
        export_by_player = {
            self._row_player_id(row): row
            for row in export_rows
            if self._row_player_id(row) is not None
        }
        issues: list[SeasonSnapshotValidationIssue] = []
        for db_row in db_rows:
            player_id = self._row_player_id(db_row)
            if player_id is None:
                continue
            export_row = export_by_player.get(player_id, {})
            for stat in stats:
                export_value = self._counting_value(export_row, stat)
                db_value = self._counting_value(db_row, stat)
                if export_value < db_value:
                    issues.append(
                        SeasonSnapshotValidationIssue(
                            category=category,
                            player_id=player_id,
                            player_name=self._validation_player_name(db_row, export_row),
                            stat=stat,
                            export_value=export_value,
                            db_value=db_value,
                        )
                    )
        return tuple(issues)

    @staticmethod
    def _row_player_id(row: dict[str, Any]) -> int | None:
        raw = row.get("player_id", row.get("id"))
        if raw is None:
            return None
        return int(raw)

    @staticmethod
    def _counting_value(row: dict[str, Any], stat: str) -> int:
        return int(row.get(stat, 0) or 0)

    @staticmethod
    def _validation_player_name(
        db_row: dict[str, Any], export_row: dict[str, Any]
    ) -> str:
        for row in (db_row, export_row):
            for key in ("name", "full_name"):
                value = str(row.get(key) or "").strip()
                if value:
                    return value
        player_id = db_row.get("player_id", db_row.get("id", ""))
        return str(player_id)

    def read_season_snapshot_dir(
        self, directory: str | Path, *, season: int
    ) -> SeasonExportSnapshot:
        """Read the standard export files of a snapshot directory. Never writes.

        Only the files that are actually present are read, so a directory that
        holds batting stats alone yields a batting-only snapshot (the checker
        then keeps its DB totals for pitching). Raises
        :class:`ExportFileMissingError` when neither file is there.
        """
        base = Path(directory)
        batting_path = base / SNAPSHOT_BATTING_FILENAME
        pitching_path = base / SNAPSHOT_PITCHING_FILENAME
        found_batting = batting_path.is_file()
        found_pitching = pitching_path.is_file()
        if not found_batting and not found_pitching:
            raise ExportFileMissingError(
                tr("No OOTP stats export was found in: {path}").format(path=base)
            )
        return self.read_season_snapshot(
            season=season,
            batting_path=batting_path if found_batting else None,
            pitching_path=pitching_path if found_pitching else None,
        )

    def read_season_snapshot(
        self,
        *,
        season: int,
        batting_path: str | Path | None = None,
        pitching_path: str | Path | None = None,
    ) -> SeasonExportSnapshot:
        """Parse export files into read-only season totals. Never writes.

        Raises an :class:`ExportSnapshotError` subclass with a user-facing
        message when a file is missing (:class:`ExportFileMissingError`), empty
        (:class:`ExportFileEmptyError`) or unparseable
        (:class:`ExportParseError`). A file that simply carries no MLB rows for
        ``season`` yields an empty category rather than an error.
        """
        if not batting_path and not pitching_path:
            raise ExportFileMissingError(
                tr("No export file was selected. Choose the OOTP stats files and retry.")
            )

        batting: tuple[dict[str, Any], ...] = ()
        pitching: tuple[dict[str, Any], ...] = ()
        sources: list[str] = []
        kinds: list[str] = []
        for kind, raw_path in (("batting", batting_path), ("pitching", pitching_path)):
            if not raw_path:
                continue
            path = Path(raw_path)
            rows = self._read_snapshot_rows(path, kind)
            totals = self._filter_and_aggregate(
                rows,
                season_filter="eq",
                current_season=season,
                target_season=season,
            )
            teams = self._snapshot_teams(rows, season)
            if kind == "batting":
                batting = tuple(
                    self._snapshot_batting_row(player_id, row, teams.get(player_id, ""))
                    for (player_id, _season), row in sorted(totals.items())
                )
            else:
                pitching = tuple(
                    self._snapshot_pitching_row(player_id, row, teams.get(player_id, ""))
                    for (player_id, _season), row in sorted(totals.items())
                )
            sources.append(str(path))
            kinds.append(kind)

        return SeasonExportSnapshot(
            season=season,
            batting=batting,
            pitching=pitching,
            sources=tuple(sources),
            kinds=tuple(kinds),
        )

    def _read_snapshot_rows(self, path: Path, kind: str) -> list[dict[str, Any]]:
        try:
            if not path.is_file():
                raise ExportFileMissingError(
                    tr("Export file not found: {path}").format(path=path)
                )
            if path.stat().st_size == 0:
                raise ExportFileEmptyError(
                    tr("The export file is empty: {path}").format(path=path)
                )
        except OSError as exc:
            raise ExportParseError(
                tr("The export file cannot be read: {path} ({error})").format(
                    path=path, error=exc
                )
            ) from exc

        col_names = BATTING_COLS if kind == "batting" else PITCHING_COLS
        try:
            rows = self._parse_file(path, col_names)
        except Exception as exc:
            raise ExportParseError(
                tr("The export file could not be parsed: {path} ({error})").format(
                    path=path, error=exc
                )
            ) from exc
        if not rows:
            raise ExportFileEmptyError(
                tr("The export file has no data rows: {path}").format(path=path)
            )
        return rows

    @staticmethod
    def _snapshot_teams(rows: list[dict[str, Any]], season: int) -> dict[int, str]:
        teams: dict[int, str] = {}
        for row in rows:
            if not is_ootp_mlb_league_row(row) or int(row["season"]) != season:
                continue
            abbr = str(row.get("team_abbr") or "").strip()
            if abbr:
                teams[int(row["player_id"])] = abbr
        return teams

    def _snapshot_batting_row(
        self, player_id: int, totals: dict[str, Any], team: str
    ) -> dict[str, Any]:
        ab = int(totals.get("ab", 0) or 0)
        hits = int(totals.get("h", 0) or 0)
        doubles = int(totals.get("doubles", 0) or 0)
        triples = int(totals.get("triples", 0) or 0)
        hr = int(totals.get("hr", 0) or 0)
        bb = int(totals.get("bb", 0) or 0)
        hbp = int(totals.get("hbp", 0) or 0)
        total_bases = (hits - doubles - triples - hr) + 2 * doubles + 3 * triples + 4 * hr
        on_base_denom = ab + bb + hbp
        # Same formulas the aggregator uses for DB-derived season totals, so an
        # overridden judgement stays comparable with an un-overridden one.
        obp_raw = (hits + bb + hbp) / on_base_denom if on_base_denom else None
        slg_raw = total_bases / ab if ab else None
        return {
            "id": player_id,
            "player_id": player_id,
            "name": self._snapshot_player_name(player_id, totals),
            "full_name": "",
            "team": team,
            "ab": ab,
            "h": hits,
            "r": int(totals.get("r", 0) or 0),
            "rbi": int(totals.get("rbi", 0) or 0),
            "bb": bb,
            "hbp": hbp,
            "k": int(totals.get("k", 0) or 0),
            "hr": hr,
            "sb": int(totals.get("sb", 0) or 0),
            "doubles": doubles,
            "triples": triples,
            "avg": round(hits / ab, 3) if ab else None,
            "obp": round(obp_raw, 3) if obp_raw is not None else None,
            "slg": round(slg_raw, 3) if slg_raw is not None else None,
            "ops": (
                round(obp_raw + slg_raw, 3)
                if obp_raw is not None and slg_raw is not None
                else None
            ),
            "games_played": int(totals.get("g", 0) or 0),
        }

    def _snapshot_pitching_row(
        self, player_id: int, totals: dict[str, Any], team: str
    ) -> dict[str, Any]:
        ip_outs = int(totals.get("ip_outs", 0) or 0)
        er = int(totals.get("er", 0) or 0)
        bb = int(totals.get("bb", 0) or 0)
        hits = int(totals.get("ha", 0) or 0)
        return {
            "id": player_id,
            "player_id": player_id,
            "name": self._snapshot_player_name(player_id, totals),
            "full_name": "",
            "team": team,
            "ip_outs": ip_outs,
            "ip": outs_to_ip_float(ip_outs),
            "h": hits,
            "er": er,
            "bb": bb,
            "k": int(totals.get("k", 0) or 0),
            "hr": int(totals.get("hr", 0) or 0),
            "w": int(totals.get("w", 0) or 0),
            "l": int(totals.get("l", 0) or 0),
            "sv": int(totals.get("s", 0) or 0),
            "gs": int(totals.get("gs", 0) or 0),
            "holds": int(totals.get("holds", 0) or 0),
            "era": round(er * 27 / ip_outs, 2) if ip_outs else None,
            "whip": round((bb + hits) / (ip_outs / 3.0), 3) if ip_outs else None,
            "games": int(totals.get("g", 0) or 0),
        }

    def _snapshot_player_name(self, player_id: int, totals: dict[str, Any]) -> str:
        """Resolve a display name without touching the players table."""
        row = self.aggregator.conn.execute(
            "SELECT COALESCE(short_name, full_name) AS name FROM players WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        if row and str(row["name"] or "").strip():
            return str(row["name"]).strip()
        first = str(totals.get("firstname", "") or "").strip()
        last = str(totals.get("lastname", "") or "").strip()
        if first and last:
            return f"{first[:1]}. {last}"
        return f"{first} {last}".strip() or str(player_id)

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

        self._sync_roster(rows, current_season)
        self._sync_team_affiliations(rows)

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
            current_rows = self._filter_and_aggregate(
                rows,
                season_filter="eq",
                current_season=current_season,
                target_season=current_season,
            )
            if persist and current_rows:
                self._save_rows(kind, current_rows, replace=True)

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

    def discover_mlb_teams_in_file(self, filepath: str | Path) -> dict[str, str]:
        path = Path(filepath)
        if not path.is_file():
            return {}
        col_names = BATTING_COLS if "batting" in path.name.lower() else PITCHING_COLS
        rows = self._parse_file(path, col_names)
        return discover_mlb_teams_from_rows(rows)

    def discover_unknown_mlb_teams(
        self,
        batting_path: str | Path | None,
        pitching_path: str | Path | None,
        known_teams: dict[str, str],
    ) -> dict[str, str]:
        discovered: dict[str, str] = {}
        for path in (batting_path, pitching_path):
            if path:
                discovered.update(self.discover_mlb_teams_in_file(path))
        return find_unknown_mlb_teams(discovered, known_teams)

    def backfill_player_names_from_file(self, filepath: str | Path) -> int:
        """Refresh players.full_name from an OOTP export (firstname + lastname)."""
        path = Path(filepath)
        if not path.is_file():
            return 0
        col_names = BATTING_COLS if "batting" in path.name.lower() else PITCHING_COLS
        rows = self._parse_file(path, col_names)
        seen: set[int] = set()
        updated = 0
        for row in rows:
            if not is_ootp_mlb_league_row(row):
                continue
            player_id = int(row["player_id"])
            if player_id in seen:
                continue
            seen.add(player_id)
            self._player_name(player_id, row)
            updated += 1
        self.aggregator.conn.commit()
        return updated

    def sync_roster_file(
        self, filepath: str | Path, current_season: int
    ) -> int:
        """Load current-season team affiliations from an export file."""
        path = Path(filepath)
        if not path.is_file():
            return 0
        col_names = BATTING_COLS if "batting" in path.name.lower() else PITCHING_COLS
        rows = self._parse_file(path, col_names)
        return self._sync_roster(rows, current_season)

    def _sync_roster(self, rows: list[dict[str, Any]], current_season: int) -> int:
        from core.teams.registry import TeamRegistry

        sync = TeamRegistry(self.aggregator.conn).sync_from_export_rows(rows)
        if sync.changed:
            self.aggregator.conn.commit()

        seasons_in_file = {
            int(row["season"])
            for row in rows
            if is_ootp_mlb_league_row(row)
        }
        seasons_to_sync: list[int] = []
        for season in (
            current_season,
            max(seasons_in_file) if seasons_in_file else current_season,
            current_season - 1,
        ):
            if season not in seasons_to_sync:
                seasons_to_sync.append(season)

        total = 0
        for season in seasons_to_sync:
            entries = self._roster_entries_for_season(rows, season)
            if not entries:
                continue
            for entry in entries:
                self._player_name(int(entry["player_id"]), entry)
            total += self.aggregator.upsert_player_roster(entries, season=season)
        return total

    def _sync_team_affiliations(self, rows: list[dict[str, Any]]) -> int:
        entries: list[dict[str, Any]] = []
        seen: set[tuple[int, int, str]] = set()
        for row in rows:
            if not is_ootp_mlb_league_row(row):
                continue
            abbr = str(row.get("team_abbr") or "").strip().upper()
            if not abbr:
                continue
            player_id = int(row["player_id"])
            season = int(row["season"])
            key = (player_id, season, abbr)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "player_id": player_id,
                    "season": season,
                    "team_abbr": abbr,
                    "team_name": str(row.get("team_name") or "").strip(),
                }
            )
        return self.aggregator.upsert_player_team_affiliations(entries)

    @staticmethod
    def _roster_entries_for_season(
        rows: list[dict[str, Any]], season: int
    ) -> list[dict[str, Any]]:
        by_player: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not is_ootp_mlb_league_row(row):
                continue
            if int(row["season"]) != season:
                continue
            abbr = str(row.get("team_abbr") or "").strip()
            if not abbr:
                continue
            player_id = int(row["player_id"])
            team_id_raw = row.get("team_id")
            team_id = int(team_id_raw) if str(team_id_raw or "").strip().isdigit() else None
            by_player[player_id] = {
                "player_id": player_id,
                "team_abbr": abbr,
                "team_name": str(row.get("team_name") or "").strip(),
                "team_id": team_id,
                "firstname": row.get("firstname", ""),
                "lastname": row.get("lastname", ""),
            }
        return list(by_player.values())

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
            if not is_ootp_mlb_league_row(row):
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

    def _korean_name_store(self):
        from core.roster.korean_names import KoreanNameStore

        if self._korean_name_store_cache is None:
            self._korean_name_store_cache = KoreanNameStore.load()
        return self._korean_name_store_cache

    def _player_name(self, player_id: int, row: dict[str, Any]) -> str:
        last_name = str(row.get("lastname", "") or "").strip()
        first_name = str(row.get("firstname", "") or "").strip()
        if is_ootp_mlb_league_row(row):
            self._korean_name_store().note_names(
                last_name, first_name, source="stats"
            )
        full_name = f"{first_name} {last_name}".strip()
        short = (
            f"{first_name[:1]}. {last_name}".strip()
            if first_name and last_name
            else full_name
        )
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
        commit_if_in_transaction(conn)
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
