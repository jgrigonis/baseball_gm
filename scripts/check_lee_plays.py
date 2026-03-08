import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get a game where Lee didn't start
cursor = conn.execute("""
    SELECT g.id
    FROM games g
    JOIN team_players tp ON (g.home_team_id = tp.team_id OR g.away_team_id = tp.team_id)
    WHERE tp.team_id = 'd9980be1a55a484b96177486ed5bea83'
    AND g.id NOT IN (
        SELECT game_id FROM player_game_stats 
        WHERE player_id = (SELECT id FROM players WHERE first_name = 'LEE' AND last_name = 'WELLS')
        AND bat_game_started = 1
    )
    LIMIT 1
""")
game_without_lee = cursor.fetchone()["game_id"]

# Check if Lee appeared at all in that game
cursor = conn.execute(
    """
    SELECT * FROM player_game_stats
    WHERE game_id = ?
    AND player_id = (SELECT id FROM players WHERE first_name = 'LEE' AND last_name = 'WELLS')
""",
    (game_without_lee,),
)

print(f"Lee Wells stats in game {game_without_lee}:", cursor.fetchone())
