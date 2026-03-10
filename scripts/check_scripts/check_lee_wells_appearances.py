import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check if Lee appeared AT ALL (even in relief) in those 19 games
cursor = conn.execute("""
    SELECT COUNT(DISTINCT game_id) as total_appearances
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'LEE' AND last_name = 'WELLS')
""")
print(
    f"Total games Lee Wells appeared in (including relief): {cursor.fetchone()['total_appearances']}"
)
