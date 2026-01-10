from src.player.player_skills import PlayerSkills

ROLE_WEIGHTS = {
    "cf": {
        "outfield": 5,
        "arm": 2,
        "speed": 3,
        "clutch": 1,
    },
    "rf": {
        "outfield": 5,
        "arm": 2,
        "speed": 1,
        "clutch": 1,
    },
    "lf": {
        "outfield": 5,
        "arm": 1,
        "speed": 1,
        "clutch": 1,
    },
    "c": {
        "catching": 5,
        "arm": 1,
        "clutch": 1,
    },
    "1b": {
        "infield": 5,
        "clutch": 1,
    },
    "2b": {
        "infield": 5,
        "speed": 1,
        "clutch": 1,
    },
    "ss": {
        "infield": 5,
        "speed": 1,
        "arm": 1,
        "clutch": 1,
    },
    "3b": {
        "infield": 5,
        "arm": 1,
        "clutch": 1,
    },
    "p": {
        "accuracy": 1,
        "stamina": 1,
        "recovery": 1,
        "ground_balls": 1,
        "strikes": 1,
        "clutch": 1,
    },
    "lead_off": {
        "speed": 1,
        "eye": 2,
        "contact": 2,
        "base_running": 1,
        "clutch": 1,
    },
    "contact_hitter": {
        "eye": 2,
        "contact": 4,
        "clutch": 1,
    },
    "power_hitter": {
        "power": 4,
        "eye": 1,
        "contact": 1,
        "clutch": 1,
    },
}

RatingMap = dict[str, int]

class PlayerEvaluator:
    @staticmethod
    def rate_player(skills: PlayerSkills) -> RatingMap:
        """
        Based on the player skills, rate the player at various
        positions and hitting styles. For instance, an outfielder's
        skill in the outfield is not just their 'outfield' rating,
        their speed, arm and clutch skill also come into play.

        Their speed will increase their range, their arm will increase
        the chance of putting out runners stretching hits, and clutch
        will increase the chances of them making a game changing play
        in the clutch.

        PlayerEvaluator is:
            stateless
            deterministic
            pure (no mutation, no randomness)
            Accepts a domain object (PlayerSkills)
        Returns a simple, serializable structure

        """
        ratings = {}

        for role, weights in ROLE_WEIGHTS.items():
            total_weight = sum(weights.values())
            score = sum(skills[k] * w for k, w in weights.items())
            ratings[role] = max(0, min(100, int(round(score / total_weight))))

        return ratings
