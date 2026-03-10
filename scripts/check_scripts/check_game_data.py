# srcipts/check_game_data.py

import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

season_id = "d9e8714621b64e539838ada9524acdf0" # This is hardcoded to a probably long gone season.

row = conn.execute(
    "SELECT COUNT(*) FROM games WHERE season_id = ?", (season_id,)
).fetchone()
print(f"Games for season: {row[0]}")

row = conn.execute(
    "SELECT COUNT(*) FROM player_game_stats pgs JOIN games g ON pgs.game_id = g.id WHERE g.season_id = ?",
    (season_id,),
).fetchone()
print(f"Player game stats joined: {row[0]}")

# Sample a game_id from player_game_stats
row = conn.execute("SELECT game_id FROM player_game_stats LIMIT 1").fetchone()
print(f"player_game_stats game_id: {row[0]}")

# Sample an id from games for that season
row = conn.execute(
    "SELECT id FROM games WHERE season_id = ? LIMIT 1", (season_id,)
).fetchone()
print(f"games id: {row[0]}")

row = conn.execute(
    "SELECT g.season_id FROM games g WHERE g.id = (SELECT game_id FROM player_game_stats LIMIT 1)"
).fetchone()
print(f"Season for that game: {row[0] if row else 'NOT FOUND'}")

rows = conn.execute("""
    SELECT season_id, COUNT(*) as total, SUM(completed) as completed
    FROM games
    GROUP BY season_id
""").fetchall()
for r in rows:
    print(f"{r['season_id']}: {r['completed']}/{r['total']} completed")

rows = conn.execute("""
    SELECT g.season_id, COUNT(*) as stat_rows
    FROM player_game_stats pgs
    JOIN games g ON pgs.game_id = g.id
    GROUP BY g.season_id
""").fetchall()
for r in rows:
    print(f"{r['season_id']}: {r['stat_rows']} stat rows")
