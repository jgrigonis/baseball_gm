import sqlite3
from pathlib import Path

from src.player.player_skills import PlayerSkills

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get ratings for the three players competing for 9th spot
for player_name in [("LEE", "WELLS"), ("ANDREW", "WELLENDORF"), ("TERRY", "SMTIH")]:
    cursor = conn.execute(
        """
        SELECT ps.*
        FROM player_skills ps
        JOIN players p ON ps.player_id = p.id
        WHERE p.first_name = ? AND p.last_name = ?
    """,
        player_name,
    )

    skills = cursor.fetchone()
    skills_obj = PlayerSkills(
        clutch=skills["clutch"],
        speed=skills["speed"],
        power=skills["power"],
        eye=skills["eye"],
        contact=skills["contact"],
        base_running=skills["base_running"],
        bunting=skills["bunting"],
        catching=skills["catching"],
        infield=skills["infield"],
        outfield=skills["outfield"],
        arm=skills["arm"],
        accuracy=skills["accuracy"],
        stamina=skills["stamina"],
        recovery=skills["recovery"],
        ground_balls=skills["ground_balls"],
        strikes=skills["strikes"],
    )

    from src.player.player_evaluator import PlayerEvaluator

    ratings = PlayerEvaluator.rate_player(skills_obj)

    print(
        f"{player_name[0]} {player_name[1]}: overall_offense={ratings['overall_offense']}, overall_player={ratings['overall_player']}"
    )
