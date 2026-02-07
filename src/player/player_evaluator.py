# src/player/player_evaluator.py

from src.player.player_skills import PlayerSkills

EXPECTED_RATINGS = {
    "cf",
    "rf",
    "lf",
    "c",
    "1b",
    "2b",
    "ss",
    "3b",
    "p",
    "lead_off",
    "contact_hitter",
    "power_hitter",
    "speed_runner",
    "defensive_value",
    "overall_offense",
    "overall_player",
}

# Weight values:
# - Higher weight = more important to the role
# - Weights are relative within each role
# - Final rating is weighted average, scaled 0-100
ROLE_WEIGHTS: dict[str, dict[str, int]] = {
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
        # "clutch": 1,
        "power": 4,
        "eye": 2,
        "contact": 3,
        "base_running": 2,
        # "bunting": 1,
        "speed": 3,
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
        Args:
            skills: Player's skills

        Returns a simple, serializable structure

        """
        ratings = {}

        for role, weights in ROLE_WEIGHTS.items():
            ratings[role] = PlayerEvaluator._calculate_weighted_rating(skills, weights)

        # --- Overall Player (offense + arm + speed + best defense) ---
        defensive_value = max(
            skills.as_dict().get("infield", 0),
            skills.as_dict().get("outfield", 0),
            skills.as_dict().get("catching", 0),
        )
        ratings["defensive_value"] = defensive_value

        overall_weights = ROLE_WEIGHTS["overall_offense"].copy()
        overall_weights["arm"] = 1  # Add arm to the offense weights

        overall_player_score = sum(skills[k] * w for k, w in overall_weights.items())
        overall_player_score += defensive_value * 3

        total_weight = sum(overall_weights.values()) + 3  # +3 for defensive_value

        ratings["overall_player"] = max(
            0, min(100, int(round(overall_player_score / total_weight)))
        )

        return ratings

    @staticmethod
    def _calculate_weighted_rating(
        skills: PlayerSkills, weights: dict[str, int]
    ) -> int:
        """Calculate a weighted rating from skills."""
        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0
        score = sum(skills[skill] * weight for skill, weight in weights.items())
        return max(0, min(100, int(round(score / total_weight))))

    @staticmethod
    def validate_weights() -> None:
        """Validate that all weights reference valid skills."""
        from src.player.skill_map import ALL_SKILL_NAMES

        for role, weights in ROLE_WEIGHTS.items():
            for skill in weights.keys():
                if skill not in ALL_SKILL_NAMES:
                    raise ValueError(f"Invalid skill '{skill}' in role '{role}'")

    @staticmethod
    def get_best_position(ratings: RatingMap) -> str:
        """Return the position where player rates highest."""
        position_ratings = {
            pos: rating
            for pos, rating in ratings.items()
            if pos in {"cf", "rf", "lf", "c", "1b", "2b", "ss", "3b", "p"}
        }
        return max(position_ratings, key=position_ratings.get)

    @staticmethod
    def get_best_batting_role(ratings: RatingMap) -> str:
        """Return the best batting role for this player."""
        batting_roles = {
            role: rating
            for role, rating in ratings.items()
            if role in {"lead_off", "contact_hitter", "power_hitter"}
        }
        return max(batting_roles, key=batting_roles.get)

    @staticmethod
    def format_ratings(ratings: RatingMap) -> str:
        """Format ratings for display."""
        lines = []
        lines.append("DEFENSIVE POSITIONS:")
        for pos in ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf", "p"]:
            lines.append(f"  {pos:3s}: {ratings.get(pos, 0):3d}")

        lines.append("\nOFFENSIVE ROLES:")
        for role in ["lead_off", "contact_hitter", "power_hitter"]:
            lines.append(f"  {role:15s}: {ratings.get(role, 0):3d}")

        lines.append("\nOVERALL:")
        lines.append(f"  Offense: {ratings.get('overall_offense', 0):3d}")
        lines.append(f"  Overall: {ratings.get('overall_player', 0):3d}")

        return "\n".join(lines)


# Call at module load time
PlayerEvaluator.validate_weights()
