from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills

terry_skills = PlayerSkills(
    clutch=48,
    speed=69,
    power=25,
    eye=54,
    contact=70,
    base_running=55,
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

ratings = PlayerEvaluator.rate_player(terry_skills)
print(f"Terry's overall_offense: {ratings['overall_offense']}")
print(f"Terry's overall_player: {ratings['overall_player']}")
