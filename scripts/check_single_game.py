import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, f.position, f.putouts, f.assists, f.errors
    FROM player_game_fielding f
    JOIN players p ON p.id = f.player_id
    WHERE f.game_id = (SELECT id FROM games WHERE completed = 1 LIMIT 1)
    ORDER BY f.position, p.last_name
    """
)
rows = cursor.fetchall()

print(f"{'Last Name':<15} {'First Name':<12} {'Pos':>4} {'PO':>4} {'A':>4} {'E':>4}")
print("-" * 45)
for row in rows:
    print(
        f"{row['last_name']:<15} {row['first_name']:<12} {row['position']:>4} {row['putouts']:>4} {row['assists']:>4} {row['errors']:>4}"
    )

cursor = conn.execute(
    """
    SELECT g.id as game_id, p.first_name, p.last_name, f.position, f.putouts, f.assists, f.errors
    FROM player_game_fielding f
    JOIN players p ON p.id = f.player_id
    JOIN games g ON g.id = f.game_id
    WHERE p.last_name IN ('HARSHMAN', 'MCDANIEL')
    ORDER BY p.last_name, g.id, f.position
    LIMIT 40
    """
)
rows = cursor.fetchall()

print(f"{'Last Name':<12} {'Game':<10} {'Pos':>4} {'PO':>4} {'A':>4} {'E':>4}")
print("-" * 42)
for row in rows:
    print(
        f"{row['last_name']:<12} {row['game_id'][-8:]:<10} {row['position']:>4} {row['putouts']:>4} {row['assists']:>4} {row['errors']:>4}"
    )
