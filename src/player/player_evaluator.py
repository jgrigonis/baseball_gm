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
    "speed_runner": {
        "speed": 2,
        "base_running": 1,
    },
    # This one is most likely subject to change
    "overall_offense": {
        # "clutch": 0,
        "power": 3,
        "eye": 1,
        "contact": 2,
        "base_running": 1,
        # "bunting": 0,
        "speed": 2,
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
            # make this code defensive against missing skills
            skills_map = skills.as_dict()
            score = sum(skills_map.get(k, 0) * w for k, w in weights.items())
            # score = sum(skills[k] * w for k, w in weights.items())
            ratings[role] = max(0, min(100, int(round(score / total_weight))))

        # --- Overall Player (offense + arm + speed + best defense) ---
        defensive_value = max(
            skills.as_dict().get("infield", 0),
            skills.as_dict().get("outfield", 0),
            skills.as_dict().get("catching", 0),
        )

        overall_player_score = (
            skills["power"] * 3
            + skills["eye"] * 1
            + skills["contact"] * 2
            + skills["base_running"] * 1
            + skills["speed"] * 2
            + skills["arm"] * 1
            + defensive_value * 3
        )

        total_weight = 3 + 1 + 2 + 1 + 2 + 1 + 3

        ratings["overall_player"] = max(
            0, min(100, int(round(overall_player_score / total_weight)))
        )

        return ratings

    # def offensive_profile(player):
    #     """Return the offensive profile for a player."""
    #     s = player.skills
    #     return {
    #         "on_base": 0.5 * s["contact"] + 0.4 * s["eye"] + 0.1 * s["clutch"],
    #         "power": s["power"],
    #         "speed": 0.6 * s["speed"] + 0.4 * s["base_running"],
    #         "bat_control": 0.7 * s["contact"] + 0.3 * s["bunting"],
    #         "contact": s["contact"],
    #         "overall": (
    #             0.35 * s["contact"]
    #             + 0.30 * s["power"]
    #             + 0.20 * s["eye"]
    #             + 0.10 * s["speed"]
    #             + 0.05 * s["clutch"]
    #         ),
    #     }
