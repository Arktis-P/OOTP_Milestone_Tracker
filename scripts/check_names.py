import sqlite3
c = sqlite3.connect("data/records.db")
for r in c.execute(
    "SELECT player_id, full_name, short_name FROM players WHERE short_name LIKE 'J. Lee' LIMIT 8"
):
    print(r)
