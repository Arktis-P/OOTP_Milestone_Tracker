"""Merge unique FirstName/LastName values into Korean mapping seed CSVs.

Sources (union):
  - Nation == South Korea, kbo_rosters, or League contains KBO
  - MLB active roster (League Name == Major League Baseball)

Existing rows and filled ``korean`` values are preserved.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.roster.combined import load_combined_roster, resolve_combined_paths
from core.roster.korean_names import KoreanNameStore
from core.roster.row_access import row_get


def is_korean_priority_player(row: list[str], fieldnames: list[str], source: str) -> bool:
    nation = row_get(row, fieldnames, "Nation").strip()
    league = row_get(row, fieldnames, "League Name").strip()
    if nation == "South Korea":
        return True
    if source == "kbo":
        return True
    return "KBO" in league


def is_mlb_active_player(row: list[str], fieldnames: list[str], source: str) -> bool:
    if source != "mlb":
        return False
    return row_get(row, fieldnames, "League Name").strip() == "Major League Baseball"


def collect_name_parts(import_export_dir: str | Path) -> tuple[set[str], set[str]]:
    mlb_path, kbo_path = resolve_combined_paths(import_export_dir)
    if not mlb_path and not kbo_path:
        raise FileNotFoundError("mlb_rosters / kbo_rosters 파일을 찾을 수 없습니다.")

    combined = load_combined_roster(mlb_path, kbo_path)
    fieldnames = combined.fieldnames

    last_names: set[str] = set()
    first_names: set[str] = set()
    for player in combined.players:
        if not (
            is_korean_priority_player(player.row, fieldnames, player.source)
            or is_mlb_active_player(player.row, fieldnames, player.source)
        ):
            continue
        last = row_get(player.row, fieldnames, "LastName").strip()
        first = row_get(player.row, fieldnames, "FirstName").strip()
        if last:
            last_names.add(last)
        if first:
            first_names.add(first)
    return last_names, first_names


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--import-export-dir",
        type=Path,
        default=root / "samples" / "roster",
        help="mlb_rosters / kbo_rosters 가 있는 폴더",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=root / "data",
        help="매핑 CSV 폴더",
    )
    args = parser.parse_args()

    last_names, first_names = collect_name_parts(args.import_export_dir)
    store = KoreanNameStore.load(args.data_dir)
    last_added, first_added = store.merge_seed_names(last_names, first_names)
    print(
        f"last names: {len(store.last_names):,} total (+{last_added:,} new) "
        f"-> {args.data_dir / 'korean_last_names.csv'}"
    )
    print(
        f"first names: {len(store.first_names):,} total (+{first_added:,} new) "
        f"-> {args.data_dir / 'korean_first_names.csv'}"
    )


if __name__ == "__main__":
    main()
