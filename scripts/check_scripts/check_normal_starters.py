import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Who are the usual 9 starters (the ones who started 174 or close to 174 games)?
cursor = conn.execute("""
    SELECT p.first_name, p.last_name, COUNT(*) as games_started
    FROM player_game_stats pgs
    JOIN players p ON pgs.player_id = p.id
    WHERE pgs.team_id = 'd9980be1a55a484b96177486ed5bea83'
    AND pgs.bat_game_started = 1
    GROUP BY p.id
    HAVING games_started > 100
    ORDER BY games_started DESC
""")

print("Usual starters (100+ games):")
usual_starters = []
for row in cursor:
    name = f"{row['first_name']} {row['last_name']}"
    usual_starters.append(name)
    print(f"  {name}: {row['games_started']} games")

# Who from the usual starters is missing from Terry's game?
game_starters = [
    "CURTIS LAMPROS",
    "GEORGE RINDERKNECHT",
    "DOMINIQUE ATKINS",
    "JAMES EVANGELISTA",
    "DANNY BRAY",
    "RAYMOND MANGUAL",
    "RUDY BANKER",
    "TERRY SMTIH",
    "MARK NOVINGER",
]

print("\nUsual starters NOT in this game:")
for starter in usual_starters:
    if starter not in game_starters:
        print(f"  {starter}")
