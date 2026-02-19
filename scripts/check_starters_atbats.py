import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check if these "starters" actually had at-bats
cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, 
           pgs.bat_game_started, pgs.bat_game_played, pgs.bat_ab
    FROM player_game_stats pgs
    JOIN players p ON pgs.player_id = p.id
    WHERE pgs.game_id = ?
    ORDER BY pgs.bat_ab DESC
""",
    ("128da1d-656f-4989-af7e-068bda60d217",),
)

print("\nAll players in that game:")
for row in cursor:
    print(
        f"  {row['first_name']} {row['last_name']}: "
        f"Started={row['bat_game_started']}, Played={row['bat_game_played']}, AB={row['bat_ab']}"
    )
