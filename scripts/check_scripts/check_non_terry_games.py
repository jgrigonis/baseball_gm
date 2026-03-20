# scripts/check_non_terry_games.py
import sqlite3
from pathlib import Path

from src.db.connection import get_connection
conn = get_connection()

# Check a sample of games Terry DIDN'T play in
cursor = conn.execute(
    """
    SELECT g.id, g.date, 
           CASE WHEN g.home_team_id = tp.team_id THEN 'home' ELSE 'away' END as home_away
    FROM games g
    JOIN team_players tp ON (g.home_team_id = tp.team_id OR g.away_team_id = tp.team_id)
    JOIN players p ON tp.player_id = p.id
    WHERE p.first_name = 'TERRY' AND p.last_name = 'SMTIH'
    AND g.completed = 1
    AND g.id NOT IN (
        SELECT game_id FROM player_game_stats 
        WHERE player_id = p.id
    )
    LIMIT 5
"""
)
print("Games Terry's team played but Terry didn't:")
for row in cursor:
    print(f"  Game {row['id']} on {row['date']} ({row['home_away']})")

# Check who DID play 2B in those games
cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, COUNT(*) as games
    FROM player_game_stats pgs
    JOIN players p ON pgs.player_id = p.id
    JOIN team_players tp1 ON p.id = tp1.player_id
    JOIN team_players tp2 ON tp2.player_id = '3468615f7460a494e37cfb9cae8c0cb8'
    WHERE tp1.team_id = tp2.team_id
    AND pgs.bat_game_started = 1
    GROUP BY p.id
    ORDER BY games DESC
    LIMIT 10
"""
)
print("\nPlayers who started games on Terry's team:")
for row in cursor:
    print(f"  {row['first_name']} {row['last_name']}: {row['games']} games started")
