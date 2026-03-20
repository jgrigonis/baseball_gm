

from src.player.player_skills import PlayerSkills

from src.db.connection import get_connection

conn = get_connection()


# Check if Lee Wells ever started as a pitcher
cursor = conn.execute(
    """
    SELECT COUNT(*) as games_started_pitching
    FROM player_game_stats
    WHERE player_id = (SELECT id FROM players WHERE first_name = 'LEE' AND last_name = 'WELLS')
    AND pitch_game_started = 1
"""
)
print(
    f"Games Lee Wells started as pitcher: {cursor.fetchone()['games_started_pitching']}"
)

# Check his SP rating
lee_skills = PlayerSkills(
    clutch=45,
    speed=94,
    power=30,
    eye=36,
    contact=37,
    base_running=51,
    bunting=55,
    catching=16,
    infield=22,
    outfield=27,
    arm=55,
    accuracy=55,
    stamina=67,
    recovery=63,
    ground_balls=64,
    strikes=51,
)

from src.player.player_evaluator import PlayerEvaluator

ratings = PlayerEvaluator.rate_player(lee_skills)
print(f"Lee Wells SP rating: {ratings['sp']}")
