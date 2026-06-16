"""Delete and recreate records.db with empty tables."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config.settings_manager import SettingsManager, resolve_data_path
from core.db.meta import get_meta
from core.db.reset import reset_save_database


def main() -> int:
    settings_path = ROOT / "data" / "settings.json"
    settings = SettingsManager(settings_path).load()
    db_path = resolve_data_path(settings.db_path)

    if db_path.is_file():
        print(f"Deleting: {db_path}")
    reset_save_database(db_path)

    conn = sqlite3.connect(db_path)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    print("Recreated tables:")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")
    print(f"init_season_coverage: {get_meta(conn, 'init_season_coverage')}")
    conn.close()

    if settings_path.is_file():
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
        raw["import_state"] = {"boxscore_dir": "", "last_import_at": ""}
        settings_path.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("Reset settings.json import_state")

    print("Done - DB is empty and ready for import.")
    print("Next: 1) 초기값 설정 (최초 설정)  2) 박스스코어 가져오기 (MLB만 체크)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
