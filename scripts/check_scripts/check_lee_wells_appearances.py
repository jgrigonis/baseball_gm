import sqlite3
from pathlib import Path

from src.db.connection import get_connection
conn = get_connection()

# Check if Lee appeared AT ALL (even in relief) in those 19 games
cursor = conn.execute(
    """
    SELECT COUNT(DISTINCT game_id) as total_appearances
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'LEE' AND last_name = 'WELLS')
"""
)
print(
    f"Total games Lee Wells appeared in (including relief): {cursor.fetchone()['total_appearances']}"
)
