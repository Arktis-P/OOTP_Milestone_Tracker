"""Export unique FirstName/LastName values for Korean-priority roster players.

Source players (union):
  - Nation == South Korea
  - listed in kbo_rosters.txt
  - League Name contains "KBO"

Outputs two minimal CSVs for manual Korean mapping:
  - korean_last_names.csv  (last_name, korean)
  - korean_first_names.csv (first_name, korean)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.roster.combined import load_combined_roster, resolve_combined_paths
from core.roster.row_access import row_get


def is_korean_priority_player(row: list[str], fieldnames: list[str], source: str) -> bool:
    nation = row_get(row, fieldnames, "Nation").strip()
    league = row_get(row, fieldnames, "League Name").strip()
    if nation == "South Korea":
        return True
    if source == "kbo":
        return True
    return "KBO" in league


def _write_name_csv(path: Path, key: str, names: set[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted((name for name in names if name), key=str.casefold)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[key, "korean"])
        writer.writeheader()
        for name in rows:
            writer.writerow({key: name, "korean": ""})
    return len(rows)


def export_korean_name_parts(
    import_export_dir: str | Path,
    data_dir: str | Path,
) -> tuple[int, int]:
    mlb_path, kbo_path = resolve_combined_paths(import_export_dir)
    if not mlb_path and not kbo_path:
        raise FileNotFoundError("mlb_rosters / kbo_rosters 파일을 찾을 수 없습니다.")

    combined = load_combined_roster(mlb_path, kbo_path)
    fieldnames = combined.fieldnames

    last_names: set[str] = set()
    first_names: set[str] = set()
    for player in combined.players:
        if not is_korean_priority_player(player.row, fieldnames, player.source):
            continue
        last = row_get(player.row, fieldnames, "LastName").strip()
        first = row_get(player.row, fieldnames, "FirstName").strip()
        if last:
            last_names.add(last)
        if first:
            first_names.add(first)

    out_dir = Path(data_dir)
    last_count = _write_name_csv(out_dir / "korean_last_names.csv", "last_name", last_names)
    first_count = _write_name_csv(out_dir / "korean_first_names.csv", "first_name", first_names)
    return last_count, first_count


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
        help="출력 CSV 폴더",
    )
    args = parser.parse_args()

    last_count, first_count = export_korean_name_parts(args.import_export_dir, args.data_dir)
    print(f"Wrote {last_count:,} last names -> {args.data_dir / 'korean_last_names.csv'}")
    print(f"Wrote {first_count:,} first names -> {args.data_dir / 'korean_first_names.csv'}")


if __name__ == "__main__":
    main()
