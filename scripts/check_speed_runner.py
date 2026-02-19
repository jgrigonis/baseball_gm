import sqlite3
from pathlib import Path

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check speed_runner ratings
for player_name in [("LEE", "WELLS"), ("ANDREW", "WELLENDORF"), ("TERRY", "SMTIH")]:
    cursor = conn.execute(
        """
        SELECT ps.speed, ps.base_running
        FROM player_skills ps
        JOIN players p ON ps.player_id = p.id
        WHERE p.first_name = ? AND p.last_name = ?
    """,
        player_name,
    )

    skills = cursor.fetchone()
    skills_obj = PlayerSkills(
        clutch=48,
        speed=skills["speed"],
        power=25,
        eye=54,
        contact=70,
        base_running=skills["base_running"],
        bunting=79,
        catching=42,
        infield=68,
        outfield=82,
        arm=41,
        accuracy=14,
        stamina=8,
        recovery=11,
        ground_balls=12,
        strikes=10,
    )

    ratings = PlayerEvaluator.rate_player(skills_obj)
    print(
        f"{player_name[0]} {player_name[1]}: speed={skills['speed']}, base_running={skills['base_running']}, speed_runner={ratings['speed_runner']}"
    )
