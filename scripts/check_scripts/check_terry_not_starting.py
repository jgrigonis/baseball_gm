import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check one game where Terry DID start
cursor = conn.execute(
    """
    SELECT game_id 
    FROM player_game_stats 
    WHERE player_id = '3468615f7460a494e37cfb9cae8c0cb8' 
    AND bat_game_started = 1
    LIMIT 1
"""
)
game_where_terry_started = cursor.fetchone()["game_id"]
print(f"Game where Terry started: {game_where_terry_started}")

# Check who else started in that game
cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, pgs.bat_game_started
    FROM player_game_stats pgs
    JOIN players p ON pgs.player_id = p.id
    WHERE pgs.game_id = ?
    AND pgs.bat_game_started = 1
    ORDER BY p.last_name
""",
    (game_where_terry_started,),
)

print("\nStarters in that game:")
for row in cursor:
    print(f"  {row['first_name']} {row['last_name']}")
