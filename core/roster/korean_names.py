"""Roman ↔ Korean name parts for roster / MLB player display."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from core.config import ensure_user_data_dir
from core.stats.player_display import looks_abbreviated

NamePart = Literal["last", "first"]

DEFAULT_LAST_NAMES_FILE = "data/korean_last_names.csv"
DEFAULT_FIRST_NAMES_FILE = "data/korean_first_names.csv"
DEFAULT_PENDING_FILE = "data/korean_names_pending.csv"

_PART_KEY_COLUMN = {"last": "last_name", "first": "first_name"}


@dataclass(frozen=True)
class PlayerNameParts:
    first_name: str
    last_name: str
    nation: str = ""


@dataclass(frozen=True)
class PendingName:
    part: NamePart
    name: str
    source: str
    first_seen: str


@dataclass
class KoreanNameMapper:
    """Read-only view of filled Korean mappings."""

    last_names: dict[str, str] = field(default_factory=dict)
    first_names: dict[str, str] = field(default_factory=dict)

    def korean_last(self, last_name: str) -> str:
        return self.last_names.get(last_name.strip(), "")

    def korean_first(self, first_name: str) -> str:
        return self.first_names.get(first_name.strip(), "")

    def format_player_name(
        self,
        last_name: str,
        first_name: str,
        *,
        western_order: bool = False,
    ) -> str:
        """Build Korean display text from mapped name parts.

        Both parts must be mapped when both roman parts are present; otherwise
        returns empty (no partial display).

        * Korean players (``western_order=False``): 성+이름 (e.g. 김택연)
        * Others (``western_order=True``): 이름 + 공백 + 성 (e.g. 마이크 트라우트)
        """
        last_key = last_name.strip()
        first_key = first_name.strip()
        kr_last = self.korean_last(last_key) if last_key else ""
        kr_first = self.korean_first(first_key) if first_key else ""

        if last_key and first_key:
            if not (kr_last and kr_first):
                return ""
            if western_order:
                return f"{kr_first} {kr_last}"
            return f"{kr_last}{kr_first}"

        if last_key:
            return kr_last
        if first_key:
            return kr_first
        return ""

    @staticmethod
    def uses_western_name_order(nation: str) -> bool:
        return nation.strip() != "South Korea"


@dataclass
class KoreanNameStore:
    """Manage mapping CSVs and the pending-translation queue."""

    data_dir: Path
    last_names: dict[str, str] = field(default_factory=dict)
    first_names: dict[str, str] = field(default_factory=dict)
    pending: list[PendingName] = field(default_factory=list)

    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> KoreanNameStore:
        base = Path(data_dir) if data_dir is not None else ensure_user_data_dir()
        store = cls(data_dir=base)
        store.last_names = _load_part_file(base / "korean_last_names.csv", "last_name")
        store.first_names = _load_part_file(base / "korean_first_names.csv", "first_name")
        store.pending = _load_pending_file(base / "korean_names_pending.csv")
        return store

    def to_mapper(self) -> KoreanNameMapper:
        return KoreanNameMapper(
            last_names={key: value for key, value in self.last_names.items() if value},
            first_names={key: value for key, value in self.first_names.items() if value},
        )

    def pending_count(self) -> int:
        return len(self.pending)

    def is_registered(self, part: NamePart, name: str) -> bool:
        key = name.strip()
        if not key:
            return True
        table = self.last_names if part == "last" else self.first_names
        return key in table

    def has_korean_mapping(self, part: NamePart, name: str) -> bool:
        """True only when the CSV row has a non-empty Korean value."""
        key = name.strip()
        if not key:
            return True
        table = self.last_names if part == "last" else self.first_names
        return bool((table.get(key) or "").strip())

    def note_name(self, part: NamePart, name: str, *, source: str = "import") -> bool:
        """Queue a roman name if it has no Korean mapping yet. Returns True if queued."""
        key = name.strip()
        if not key or self.has_korean_mapping(part, key):
            return False
        if any(item.part == part and item.name == key for item in self.pending):
            return False
        today = date.today().isoformat()
        self.pending.append(PendingName(part=part, name=key, source=source, first_seen=today))
        self._save_pending()
        return True

    def note_parts_if_unmapped(
        self,
        parts: PlayerNameParts,
        *,
        source: str = "import",
    ) -> int:
        """Queue any name parts that are known but not yet translated."""
        added = 0
        if parts.last_name and self.note_name("last", parts.last_name, source=source):
            added += 1
        if parts.first_name and self.note_name("first", parts.first_name, source=source):
            added += 1
        return added

    def note_names(
        self,
        last_name: str,
        first_name: str,
        *,
        source: str = "import",
    ) -> int:
        added = 0
        if self.note_name("last", last_name, source=source):
            added += 1
        if self.note_name("first", first_name, source=source):
            added += 1
        return added

    def note_from_full_name(
        self,
        full_name: str,
        *,
        source: str = "boxscore",
        player_id: int | None = None,
        roster_names: dict[int, PlayerNameParts] | None = None,
        nation: str = "",
    ) -> int:
        parts = resolve_player_name_parts(
            full_name=full_name,
            player_id=player_id,
            roster_names=roster_names,
            nation=nation,
        )
        if not parts.first_name and not parts.last_name:
            return 0
        return self.note_parts_if_unmapped(parts, source=source)

    def apply_mapping(self, part: NamePart, name: str, korean: str) -> None:
        key = name.strip()
        value = korean.strip()
        if not key or not value:
            raise ValueError("이름과 한글 표기를 모두 입력하세요.")
        table = self.last_names if part == "last" else self.first_names
        table[key] = value
        self._save_part(part)
        self.pending = [
            item for item in self.pending if not (item.part == part and item.name == key)
        ]
        self._save_pending()

    def merge_seed_names(
        self,
        last_names: set[str],
        first_names: set[str],
    ) -> tuple[int, int]:
        """Add new roman names to mapping files without overwriting existing rows."""
        last_added = _merge_into(self.last_names, last_names)
        first_added = _merge_into(self.first_names, first_names)
        if last_added:
            self._save_part("last")
        if first_added:
            self._save_part("first")
        return last_added, first_added

    def _save_part(self, part: NamePart) -> None:
        key_column = _PART_KEY_COLUMN[part]
        table = self.last_names if part == "last" else self.first_names
        path = self.data_dir / (
            "korean_last_names.csv" if part == "last" else "korean_first_names.csv"
        )
        _write_part_file(path, key_column, table)

    def _save_pending(self) -> None:
        path = self.data_dir / "korean_names_pending.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(
            self.pending,
            key=lambda item: (item.part != "last", item.name.casefold()),
        )
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["part", "name", "source", "first_seen"]
            )
            writer.writeheader()
            for item in rows:
                writer.writerow(
                    {
                        "part": item.part,
                        "name": item.name,
                        "source": item.source,
                        "first_seen": item.first_seen,
                    }
                )


def split_ootp_full_name(full_name: str) -> tuple[str, str]:
    """Split stats-style ``First Last`` into first/last name parts."""
    text = full_name.strip()
    if not text or looks_abbreviated(text):
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def note_players_from_boxscore_import(
    aggregator,
    game_ids: list[int],
    *,
    import_export_dir: str | Path | None = None,
) -> int:
    """Queue unmapped name parts for MLB players seen in imported games."""
    if not game_ids:
        return 0
    placeholders = ",".join("?" for _ in game_ids)
    rows = aggregator.conn.execute(
        f"""
        SELECT DISTINCT p.player_id, p.full_name
        FROM players p
        JOIN (
            SELECT player_id, game_id FROM batting_logs WHERE game_id IN ({placeholders})
            UNION
            SELECT player_id, game_id FROM pitching_logs WHERE game_id IN ({placeholders})
        ) seen ON seen.player_id = p.player_id
        JOIN games g ON g.game_id = seen.game_id AND g.is_mlb = 1
        """,
        [*game_ids, *game_ids],
    ).fetchall()
    roster_names = load_roster_player_names(import_export_dir)
    nations = load_player_nations(import_export_dir)
    store = KoreanNameStore.load()
    added = 0
    for row in rows:
        player_id = int(row["player_id"])
        added += store.note_from_full_name(
            str(row["full_name"] or ""),
            source="boxscore",
            player_id=player_id,
            roster_names=roster_names,
            nation=nations.get(player_id, ""),
        )
    return added


def _merge_into(table: dict[str, str], names: set[str]) -> int:
    added = 0
    for name in names:
        key = name.strip()
        if key and key not in table:
            table[key] = ""
            added += 1
    return added


def _load_part_file(path: Path, key_column: str) -> dict[str, str]:
    if not path.is_file():
        return {}
    table: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or key_column not in reader.fieldnames:
            return {}
        for row in reader:
            key = (row.get(key_column) or "").strip()
            if key:
                table[key] = (row.get("korean") or "").strip()
    return table


def _write_part_file(path: Path, key_column: str, table: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(table.items(), key=lambda item: item[0].casefold())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[key_column, "korean"])
        writer.writeheader()
        for key, value in rows:
            writer.writerow({key_column: key, "korean": value})


def _load_pending_file(path: Path) -> list[PendingName]:
    if not path.is_file():
        return []
    pending: list[PendingName] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        for row in reader:
            part = (row.get("part") or "").strip()
            name = (row.get("name") or "").strip()
            if part not in ("last", "first") or not name:
                continue
            pending.append(
                PendingName(
                    part=part,  # type: ignore[arg-type]
                    name=name,
                    source=(row.get("source") or "").strip() or "import",
                    first_seen=(row.get("first_seen") or "").strip(),
                )
            )
    return pending


def pending_full_name_label(item: PendingName) -> str:
    """Show how a pending part fits into an OOTP stats-style full name."""
    if item.part == "first":
        return f"{item.name} …"
    return f"… {item.name}"


def parse_display_name_parts(display_name: str) -> tuple[str, str]:
    """Return ``(first_name, last_name)`` from common OOTP display strings."""
    text = display_name.strip()
    if not text:
        return "", ""
    if "," in text:
        last, _, first = text.partition(",")
        return first.strip(), last.strip()
    first, last = split_ootp_full_name(text)
    if first or last:
        return first, last
    if looks_abbreviated(text):
        parts = text.split()
        if len(parts) >= 2:
            return "", parts[-1]
    parts = text.split()
    if len(parts) == 1:
        return "", parts[0]
    return "", ""


def resolve_player_name_parts(
    *,
    full_name: str = "",
    player_id: int | None = None,
    roster_names: dict[int, PlayerNameParts] | None = None,
    nation: str = "",
) -> PlayerNameParts:
    """Prefer non-abbreviated DB full_name; fall back to roster First/Last."""
    full = full_name.strip()
    roster = roster_names.get(player_id) if player_id and roster_names else None

    if full and not looks_abbreviated(full):
        first, last = parse_display_name_parts(full)
        return PlayerNameParts(
            first_name=first,
            last_name=last,
            nation=(roster.nation if roster else nation),
        )

    if roster and (roster.first_name or roster.last_name):
        return roster

    if full:
        first, last = parse_display_name_parts(full)
        return PlayerNameParts(first_name=first, last_name=last, nation=nation)

    return PlayerNameParts(first_name="", last_name="", nation=nation)


def format_korean_for_parts(
    parts: PlayerNameParts,
    mapper: KoreanNameMapper | None = None,
    *,
    source_name: str = "",
) -> str:
    if not parts.first_name and not parts.last_name:
        return ""
    if source_name and looks_abbreviated(source_name):
        if not (parts.first_name and parts.last_name):
            return ""
    if mapper is None:
        mapper = load_korean_name_mapper()
    return mapper.format_player_name(
        parts.last_name,
        parts.first_name,
        western_order=KoreanNameMapper.uses_western_name_order(parts.nation),
    )


def format_korean_from_full_name(
    full_name: str,
    mapper: KoreanNameMapper | None = None,
    *,
    nation: str = "",
    player_id: int | None = None,
    roster_names: dict[int, PlayerNameParts] | None = None,
) -> str:
    parts = resolve_player_name_parts(
        full_name=full_name,
        player_id=player_id,
        roster_names=roster_names,
        nation=nation,
    )
    return format_korean_for_parts(parts, mapper, source_name=full_name)


def korean_display_for_player(
    mapper: KoreanNameMapper,
    *,
    full_name: str | None,
    nation: str = "",
    player_id: int | None = None,
    roster_names: dict[int, PlayerNameParts] | None = None,
) -> str:
    return format_korean_from_full_name(
        full_name or "",
        mapper,
        nation=nation,
        player_id=player_id,
        roster_names=roster_names,
    )


def load_roster_player_names(
    import_export_dir: str | Path | None = None,
) -> dict[int, PlayerNameParts]:
    from core.roster.combined import load_combined_roster, resolve_combined_paths
    from core.roster.row_access import row_get

    mlb_path, kbo_path = resolve_combined_paths(import_export_dir or "")
    if not mlb_path and not kbo_path:
        return {}
    combined = load_combined_roster(mlb_path, kbo_path)
    fieldnames = combined.fieldnames
    names: dict[int, PlayerNameParts] = {}
    for player in combined.players:
        names[player.player_id] = PlayerNameParts(
            first_name=row_get(player.row, fieldnames, "FirstName").strip(),
            last_name=row_get(player.row, fieldnames, "LastName").strip(),
            nation=row_get(player.row, fieldnames, "Nation").strip(),
        )
    return names


def load_player_nations(import_export_dir: str | Path | None = None) -> dict[int, str]:
    return {
        player_id: parts.nation
        for player_id, parts in load_roster_player_names(import_export_dir).items()
        if parts.nation
    }


def load_player_full_names(aggregator) -> dict[int, str]:
    rows = aggregator.conn.execute(
        "SELECT player_id, full_name FROM players"
    ).fetchall()
    return {int(row["player_id"]): str(row["full_name"] or "") for row in rows}


# Backward-compatible helper used by bulk rating dialog.
def load_korean_name_mapper(data_dir: str | Path | None = None) -> KoreanNameMapper:
    return KoreanNameStore.load(data_dir).to_mapper()
