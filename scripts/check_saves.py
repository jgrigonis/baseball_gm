import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
season_id = "80eaa151d327482ebb2db47cdf7088ef"

cursor = conn.execute(
    """
    SELECT SUM(pitch_save) as total_saves
    FROM player_game_stats pgs
    JOIN games g ON pgs.game_id = g.id
    WHERE g.season_id = ?
    """,
    (season_id,),
)
print(f"Total saves in DB: {cursor.fetchone()['total_saves']}")
