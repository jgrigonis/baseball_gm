# scripts/check_stats.py
"""
Check the stats for a specific player.

TERRY SMTIH
"""

import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check if they're pitchers
cursor = conn.execute(
    """
    SELECT first_name, last_name, position 
    FROM players 
    WHERE first_name = 'TERRY' AND last_name = 'SMTIH'
"""
    # TERRY SMTIH
)
print("Player info:", cursor.fetchone())

# Check how many games they played
cursor = conn.execute("""
    SELECT COUNT(DISTINCT game_id) as games_played
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'TERRY' AND last_name = 'SMTIH')
""")
print("Games played:", cursor.fetchone()["games_played"])

# Check their full batting stats
cursor = conn.execute("""
    SELECT 
        SUM(bat_ab) as AB,
        SUM(bat_hits) as H,
        SUM(bat_walks) as BB,
        SUM(bat_hbp) as HBP,
        SUM(bat_sac_flys) as SF,
        SUM(bat_game_played) as GP,
        SUM(bat_game_started) as GS
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'TERRY' AND last_name = 'SMTIH')
""")
row = cursor.fetchone()
for key in row.keys():
    print(f"{key}: {row[key]}")

conn.close()
