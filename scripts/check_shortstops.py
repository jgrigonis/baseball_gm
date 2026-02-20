import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get a game where Lee didn't start
cursor = conn.execute(
    """
    SELECT
        p.id,
        p.first_name,
        p.last_name,
        SUM(f.putouts) AS putouts,
        SUM(f.assists) AS assists,
        SUM(f.errors)  AS errors
    FROM players p
    JOIN player_game_fielding f ON p.id = f.player_id
    WHERE f.position = 'ss'
    GROUP BY p.id, p.first_name, p.last_name
    ORDER BY p.last_name, p.first_name;
"""
)
rows = cursor.fetchall()

print(f"{'Last Name':<15} {'First Name':<15} {'PO':>5} {'A':>5} {'E':>5}")
print("-" * 45)
for row in rows:
    print(
        f"{row['last_name']:<15} {row['first_name']:<15} {row['putouts']:>5} {row['assists']:>5} {row['errors']:>5}"
    )
