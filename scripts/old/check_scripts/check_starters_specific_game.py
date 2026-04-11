# scripts/check_starters_specific_game.py
import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get Terry's team
cursor = conn.execute(
    """
    SELECT pgs.team_id, t.city, t.mascot
    FROM player_game_stats pgs
    JOIN teams t ON pgs.team_id = t.id
    WHERE pgs.game_id = ?
    AND pgs.player_id = '3468615f7460a494e37cfb9cae8c0cb8'
""",
    ("8128da1d-656f-4989-af7e-068bda60d217",),
)

terry_team = cursor.fetchone()
print(
    f"Terry's team: {terry_team['city']} {terry_team['mascot']} (ID: {terry_team['team_id']})"
)

# Get just his team's starters
cursor = conn.execute(
    """
    SELECT p.first_name, p.last_name, pgs.bat_ab
    FROM player_game_stats pgs
    JOIN players p ON pgs.player_id = p.id
    WHERE pgs.game_id = ?
    AND pgs.team_id = ?
    AND pgs.bat_game_started = 1
    ORDER BY pgs.bat_ab DESC
""",
    ("8128da1d-656f-4989-af7e-068bda60d217", terry_team["team_id"]),
)

print("\nTerry's team starters in that game:")
for row in cursor:
    print(f"  {row['first_name']} {row['last_name']}: {row['bat_ab']} AB")
