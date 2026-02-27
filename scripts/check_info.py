# scripts/check_info.py
import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check which team Terry is on
cursor = conn.execute("""
    SELECT t.city, t.mascot
    FROM teams t
    JOIN team_players tp ON t.id = tp.team_id
    JOIN players p ON tp.player_id = p.id
    WHERE p.first_name = 'TERRY' AND p.last_name = 'SMTIH'
""")
print("Team:", cursor.fetchone())

# Check how many games his team played
cursor = conn.execute("""
    SELECT COUNT(*) as total_games
    FROM games g
    JOIN team_players tp ON (g.home_team_id = tp.team_id OR g.away_team_id = tp.team_id)
    JOIN players p ON tp.player_id = p.id
    WHERE p.first_name = 'TERRY' AND p.last_name = 'SMTIH'
    AND g.completed = 1
""")
print("Team's total games:", cursor.fetchone()["total_games"])

# Check Terry's ratings
cursor = conn.execute("""
    SELECT ps.*
    FROM player_skills ps
    JOIN players p ON ps.player_id = p.id
    WHERE p.first_name = 'TERRY' AND p.last_name = 'SMTIH'
""")
print("\nTerry's skills:", dict(cursor.fetchone()))
