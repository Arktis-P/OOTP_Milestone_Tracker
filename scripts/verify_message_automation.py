"""Non-destructive smoke check for `core.milestone.message_automation`.

Runs `parse_message` over every fixture in `tests/fixtures/messages/` and
prints category / excluded / exclusion_reason / form count, then asserts
that every fixture the README lists under "1차 제외" (permanently excluded)
never produces a form. Does not touch the database.

Usage:
    python scripts/verify_message_automation.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.milestone.message_automation import parse_message

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "messages"

# From tests/fixtures/messages/README.md "샘플만 두고 1차 자동화에서 제외".
PERMANENTLY_EXCLUDED_PREFIXES = (
    "postseason_wildcard_",
    "postseason_playoff_clinch_",
    "trade_deadline_news_",
    "retirement_",
)
PERMANENTLY_EXCLUDED_EXACT = {
    "award_all_star_selection_02.txt",
    "hall_of_fame_02.txt",
}


def is_permanently_excluded(filename: str) -> bool:
    if filename in PERMANENTLY_EXCLUDED_EXACT:
        return True
    return any(filename.startswith(prefix) for prefix in PERMANENTLY_EXCLUDED_PREFIXES)


def main() -> None:
    tracked_teams = ["Seoul Yukies"]
    message_date = date(2026, 10, 1)

    failures: list[str] = []
    fixture_files = sorted(FIXTURES_DIR.glob("*.txt"))
    if not fixture_files:
        raise SystemExit(f"No fixtures found under {FIXTURES_DIR}")

    for path in fixture_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_message(
            text,
            tracked_teams=tracked_teams,
            message_date=message_date,
            source_id=path.stem,
        )
        n_forms = len(parsed.forms)
        print(
            f"{path.name:40s} category={parsed.category:26s} "
            f"excluded={str(parsed.excluded):5s} reason={parsed.exclusion_reason or '-':32s} forms={n_forms}"
        )

        if is_permanently_excluded(path.name):
            if not parsed.excluded or n_forms != 0:
                failures.append(f"{path.name}: expected permanent exclusion, got excluded={parsed.excluded} forms={n_forms}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} fixture(s) violated the README '1차 제외' contract")
        for line in failures:
            print(f"  - {line}")
        raise SystemExit(1)

    print(f"OK: parsed {len(fixture_files)} fixtures, all '1차 제외' fixtures produced zero forms")


if __name__ == "__main__":
    main()
