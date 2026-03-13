import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row


cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, f.position, f.putouts, f.assists, f.errors
    FROM players p
    JOIN player_game_fielding f ON p.id = f.player_id
    WHERE p.last_name IN ('MCDANIEL', 'HARSHMAN', 'DOAKES')
    ORDER BY p.last_name, f.position;
"""
)
rows = cursor.fetchall()

print(f"{'Last Name':<15} {'First Name':<12} {'Pos':>4} {'PO':>6} {'A':>6} {'E':>4}")
print("-" * 50)
for row in rows:
    print(
        f"{row['last_name']:<15} {row['first_name']:<12} {row['position']:>4} {row['putouts']:>6} {row['assists']:>6} {row['errors']:>4}"
    )
