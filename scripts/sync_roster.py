"""Backfill player_roster from OOTP export files (run after changing tracked_teams)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import SettingsManager, resolve_data_path
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter


def main() -> None:
    settings = SettingsManager().load()
    export_dir = Path(settings.initial_stats_dir or settings.paths.get("import_export_dir", ""))
    if not export_dir.is_dir():
        print(f"export dir not found: {export_dir}")
        return

    batting = next(export_dir.glob("player_*batting*stats*.txt"), None)
    pitching = next(export_dir.glob("player_*pitching*stats*.txt"), None)
    if not batting and not pitching:
        print(f"no player stats export in {export_dir}")
        return

    db_path = resolve_data_path(settings.db_path)
    with Aggregator(db_path) as agg:
        importer = InitialImporter(agg)
        total = 0
        if batting:
            total += importer.sync_roster_file(batting, settings.current_season)
            names = importer.backfill_player_names_from_file(batting)
            print(f"batting roster rows: {batting.name} (names refreshed: {names})")
        if pitching:
            total += importer.sync_roster_file(pitching, settings.current_season)
            names = importer.backfill_player_names_from_file(pitching)
            print(f"pitching roster rows: {pitching.name} (names refreshed: {names})")
        sf = agg.conn.execute(
            "SELECT COUNT(*) FROM player_roster WHERE team_abbr = 'SF'"
        ).fetchone()[0]
        print(f"roster synced; SF players in player_roster: {sf}")


if __name__ == "__main__":
    main()
