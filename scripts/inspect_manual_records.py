"""Inspect existing manual milestone records for automation field rules."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import json

candidates = [
    Path("saves/SuperYukies_V1.0.lg_4c17d86baf/records.db"),
    Path("data/records.db"),
]
db = next((p for p in candidates if p.exists()), None)
print("DB", db)
if db is None:
    raise SystemExit(1)

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

out: dict[str, object] = {"db": str(db)}

out["manual_keys"] = [
    dict(r)
    for r in conn.execute(
        """
        SELECT milestone_key, milestone_label, scope, COUNT(*) AS c
        FROM milestone_records
        WHERE is_manual = 1 OR scope = 'manual_event'
        GROUP BY milestone_key, milestone_label, scope
        ORDER BY c DESC
        """
    )
]

out["transfers"] = [
    dict(r)
    for r in conn.execute(
        """
        SELECT mr.achieved_date, mr.milestone_key, mr.milestone_label,
               COALESCE(p.short_name, p.full_name) AS player,
               mr.team, mr.opponent_team, mr.description, mr.notes, mr.season
        FROM milestone_records mr
        LEFT JOIN players p ON p.player_id = mr.player_id
        WHERE mr.milestone_key LIKE 'manual_transfer%'
        ORDER BY mr.achieved_date DESC
        LIMIT 20
        """
    )
]

out["injuries"] = [
    dict(r)
    for r in conn.execute(
        """
        SELECT mr.achieved_date, mr.milestone_label,
               COALESCE(p.short_name, p.full_name) AS player,
               mr.team, mr.description, mr.notes, mr.season
        FROM milestone_records mr
        LEFT JOIN players p ON p.player_id = mr.player_id
        WHERE mr.milestone_key = 'manual_injury'
        ORDER BY mr.achieved_date DESC
        LIMIT 20
        """
    )
]

out["awards"] = [
    dict(r)
    for r in conn.execute(
        """
        SELECT mr.achieved_date, mr.milestone_key, mr.milestone_label,
               COALESCE(p.short_name, p.full_name) AS player,
               mr.team, mr.opponent_team, mr.opponent_player,
               mr.description, mr.notes, mr.season, mr.games_at_achievement,
               mr.player_id
        FROM milestone_records mr
        LEFT JOIN players p ON p.player_id = mr.player_id
        WHERE mr.is_manual = 1
          AND mr.milestone_key NOT LIKE 'manual_%'
        ORDER BY mr.achieved_date DESC
        LIMIT 40
        """
    )
]

path = Path("scripts/_manual_dump.json")
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", path)
print("keys", out["manual_keys"])
print("transfers", len(out["transfers"]), "injuries", len(out["injuries"]), "awards", len(out["awards"]))
