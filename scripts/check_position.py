# scripts/check_position.py
import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.execute(
    """
    SELECT first_name, last_name, position 
    FROM players 
    WHERE first_name = 'TERRY' AND last_name = 'SMTIH'
"""
)
row = cursor.fetchone()
print(f"Name: {row['first_name']} {row['last_name']}, Position: {row['position']}")

# Check his pitching stats
cursor = conn.execute(
    """
    SELECT 
        SUM(pitch_game_played) as P_GP,
        SUM(pitch_game_started) as P_GS,
        SUM(pitch_outs) as Outs,
        ROUND(SUM(pitch_outs) / 3.0, 1) as IP
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'TERRY' AND last_name = 'SMTIH')
"""
)
row = cursor.fetchone()
for key in row.keys():
    print(f"{key}: {row[key]}")
