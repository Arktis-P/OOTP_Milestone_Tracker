"""Debug tracked team filter vs DB team codes."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
s = json.loads((ROOT / "data/settings.json").read_text(encoding="utf-8"))
c = sqlite3.connect(ROOT / "data/records.db")

print("tracked_teams:", s.get("tracked_teams"))
for t in ("games", "batting_logs", "pitching_logs", "career_batting_init", "career_pitching_init"):
    print(f"{t}:", c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

print("\n--- batting_logs teams (top 25) ---")
for r in c.execute(
    "SELECT team, COUNT(*) c FROM batting_logs GROUP BY team ORDER BY c DESC LIMIT 25"
):
    print(r)

print("\n--- pitching_logs teams (top 25) ---")
for r in c.execute(
    "SELECT team, COUNT(*) c FROM pitching_logs GROUP BY team ORDER BY c DESC LIMIT 25"
):
    print(r)

for code in ("SF", "SFG", "SAN", "Giants"):
    b = c.execute("SELECT COUNT(*) FROM batting_logs WHERE team=?", (code,)).fetchone()[0]
    p = c.execute("SELECT COUNT(*) FROM pitching_logs WHERE team=?", (code,)).fetchone()[0]
    print(f"team={code!r}: batting={b}, pitching={p}")

teams = s.get("tracked_teams") or []
if teams:
    ph = ",".join("?" * len(teams))
    n = c.execute(
        f"""
        SELECT COUNT(DISTINCT player_id) FROM (
            SELECT player_id FROM batting_logs WHERE team IN ({ph})
            UNION SELECT player_id FROM pitching_logs WHERE team IN ({ph})
        )
        """,
        teams + teams,
    ).fetchone()[0]
    print(f"\ntracked filter {teams} -> {n} players")

print("\n--- games away/home sample ---")
for r in c.execute("SELECT game_id, away_team, home_team FROM games LIMIT 10"):
    print(r)

print("\n--- init coverage ---")
row = c.execute("SELECT value FROM db_meta WHERE key='init_season_coverage'").fetchone()
print("init_season_coverage:", row[0] if row else None)

for pattern in ("%San Francisco%", "%Giants%", "SF"):
    b = c.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE team LIKE ?",
        (pattern if "%" in pattern else pattern,),
    ).fetchone()[0]
    print(f"batting team match {pattern!r}: {b}")

print("\n--- init players on SF from export? (no team col in init) ---")
print("career_batting_init rows:", c.execute("SELECT COUNT(*) FROM career_batting_init").fetchone()[0])

c.close()
