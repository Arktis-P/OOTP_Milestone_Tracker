"""Import pre-tracker career stats from OOTP player stats text exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.stats.aggregator import Aggregator
from core.stats.ip_utils import ip_to_outs

BATTING_SPLIT_IDX = 27
BATTING_OOTP_PID_IDX = -2

PITCHING_SPLIT_IDX = 46
PITCHING_OOTP_PID_IDX = -2
PITCHING_IP_IDX = 10
PITCHING_CG_IDX = 35
PITCHING_SHO_IDX = 36
PITCHING_HOLDS_IDX = 37


@dataclass
class InitialImportResult:
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    total_scanned: int = 0


class InitialImporter:
    """Parse OOTP player_batting_stats / player_pitching_stats exports."""

    def __init__(self, aggregator: Aggregator) -> None:
        self.aggregator = aggregator

    def import_batting(self, filepath: str | Path) -> InitialImportResult:
        return self._import_file(filepath, kind="batting")

    def import_pitching(self, filepath: str | Path) -> InitialImportResult:
        return self._import_file(filepath, kind="pitching")

    def import_from_settings_dir(self, directory: str | Path) -> InitialImportResult:
        directory = Path(directory)
        batting = directory / "player_batting_stats.txt"
        pitching = directory / "player_pitching_stats.txt"
        combined = InitialImportResult()
        if batting.is_file():
            result = self.import_batting(batting)
            combined.imported += result.imported
            combined.skipped += result.skipped
            combined.errors.extend(result.errors)
            combined.total_scanned += result.total_scanned
        if pitching.is_file():
            result = self.import_pitching(pitching)
            combined.imported += result.imported
            combined.skipped += result.skipped
            combined.errors.extend(result.errors)
            combined.total_scanned += result.total_scanned
        return combined

    def get_init_summary(self) -> dict[str, int]:
        conn = self.aggregator.conn
        batting = conn.execute("SELECT COUNT(DISTINCT player_id) FROM career_batting_init").fetchone()
        pitching = conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM career_pitching_init"
        ).fetchone()
        return {
            "batting_players": int(batting[0] if batting else 0),
            "pitching_players": int(pitching[0] if pitching else 0),
        }

    def _import_file(self, filepath: str | Path, *, kind: str) -> InitialImportResult:
        path = Path(filepath)
        result = InitialImportResult()
        if not path.is_file():
            result.errors.append(f"File not found: {path}")
            return result

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        conn = self.aggregator.conn
        try:
            conn.execute("BEGIN")
            for line_no, raw_line in enumerate(lines, start=1):
                line = raw_line.strip()
                if not line or line.startswith("//"):
                    continue
                result.total_scanned += 1
                try:
                    fields = [part.strip() for part in line.split(",")]
                    if kind == "batting":
                        imported = self._import_batting_row(fields)
                    else:
                        imported = self._import_pitching_row(fields)
                    if imported:
                        result.imported += 1
                    else:
                        result.skipped += 1
                except Exception as exc:
                    result.errors.append(f"line {line_no}: {exc}")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            result.errors.append(str(exc))
        return result

    def _import_batting_row(self, fields: list[str]) -> bool:
        if len(fields) < abs(BATTING_OOTP_PID_IDX):
            raise ValueError("not enough columns for batting row")

        split_id = int(fields[BATTING_SPLIT_IDX])
        if split_id != 1:
            return False

        ootp_pid = int(fields[BATTING_OOTP_PID_IDX])
        season = int(fields[3])
        firstname = fields[2]
        lastname = fields[1]
        full_name = f"{firstname} {lastname}".strip()

        self.aggregator.upsert_player(ootp_pid, full_name[:1] + ". " + lastname, full_name)

        self.aggregator.conn.execute(
            """
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
            """,
            (
                ootp_pid,
                season,
                _int(fields[5]),
                _int(fields[7]),
                _int(fields[8]),
                _int(fields[9]),
                _int(fields[10]),
                _int(fields[11]),
                _int(fields[12]),
                _int(fields[13]),
                _int(fields[14]),
                _int(fields[15]),
                _int(fields[16]),
                _int(fields[17]),
                _int(fields[18]),
                _int(fields[19]),
                _int(fields[20]),
                _int(fields[21]),
                _int(fields[22]),
            ),
        )
        return True

    def _import_pitching_row(self, fields: list[str]) -> bool:
        if len(fields) < abs(PITCHING_OOTP_PID_IDX):
            raise ValueError("not enough columns for pitching row")

        split_id = int(fields[PITCHING_SPLIT_IDX])
        if split_id != 1:
            return False

        ootp_pid = int(fields[PITCHING_OOTP_PID_IDX])
        season = int(fields[3])
        firstname = fields[2]
        lastname = fields[1]
        full_name = f"{firstname} {lastname}".strip()

        self.aggregator.upsert_player(ootp_pid, full_name[:1] + ". " + lastname, full_name)

        ip_outs = ip_to_outs(fields[PITCHING_IP_IDX])
        self.aggregator.conn.execute(
            """
            INSERT INTO career_pitching_init (
                player_id, season, g, gs, w, l, s, ip_outs,
                ha, r, er, bb, hbp, k, bf, hr, cg, sho, wp, bk, holds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, season) DO UPDATE SET
                g=excluded.g, gs=excluded.gs, w=excluded.w, l=excluded.l,
                s=excluded.s, ip_outs=excluded.ip_outs, ha=excluded.ha,
                r=excluded.r, er=excluded.er, bb=excluded.bb, hbp=excluded.hbp,
                k=excluded.k, bf=excluded.bf, hr=excluded.hr, cg=excluded.cg,
                sho=excluded.sho, wp=excluded.wp, bk=excluded.bk, holds=excluded.holds
            """,
            (
                ootp_pid,
                season,
                _int(fields[5]),
                _int(fields[6]),
                _int(fields[7]),
                _int(fields[8]),
                _int(fields[9]),
                ip_outs,
                _int(fields[11]),
                _int(fields[12]),
                _int(fields[13]),
                _int(fields[14]),
                _int(fields[15]),
                _int(fields[16]),
                _int(fields[17]),
                _int(fields[22]),
                _int(fields[PITCHING_CG_IDX]),
                _int(fields[PITCHING_SHO_IDX]),
                _int(fields[29]),
                _int(fields[28]),
                _int(fields[PITCHING_HOLDS_IDX]),
            ),
        )
        return True


def _int(value: str) -> int:
    value = value.strip().strip('"')
    if not value:
        return 0
    return int(float(value))
