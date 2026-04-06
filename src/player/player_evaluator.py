# src/player/player_evaluator.py

from src.player.player_factory import VALID_THROWS
from src.player.player_skills import PlayerSkills

LEFT_HAND_CAPPED_POSITIONS = {"3b", "2b", "ss", "c"}
LEFT_HAND_CAP = 20

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
    "sp",
    "rp",
    "cp",
    "lead_off",
    "contact_hitter",
    "power_hitter",
    "speed_runner",
    "defensive_value",
    "overall_offense",
    "overall_player",
    "prospect",
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
        "durability": 1,
    },
    "rf": {
        "outfield": 5,
        "arm": 2,
        "speed": 1,
        "clutch": 1,
        "durability": 1,
    },
    "lf": {
        "outfield": 5,
        "arm": 1,
        "speed": 1,
        "clutch": 1,
        "durability": 1,
    },
    "c": {
        "catching": 5,
        "arm": 1,
        "clutch": 1,
        "durability": 1,
    },
    "1b": {
        "infield": 5,
        "clutch": 1,
        "durability": 1,
    },
    "2b": {
        "infield": 5,
        "speed": 1,
        "clutch": 1,
        "durability": 1,
    },
    "ss": {
        "infield": 5,
        "speed": 1,
        "arm": 1,
        "clutch": 1,
        "durability": 1,
    },
    "3b": {
        "infield": 5,
        "arm": 1,
        "clutch": 1,
        "durability": 1,
    },
    "p": {
        "accuracy": 1,
        "stamina": 1,
        "recovery": 1,
        "ground_balls": 1,
        "strikes": 1,
        "clutch": 1,
    },
    "sp": {
        "accuracy": 1,
        "stamina": 3,
        "recovery": 3,
        "ground_balls": 1,
        "strikes": 1,
        "clutch": 1,
    },
    "rp": {
        "accuracy": 1,
        "ground_balls": 1,
        "strikes": 1,
        "clutch": 1,
    },
    "cp": {
        "strikes": 4,
        "clutch": 3,
        "accuracy": 2,
        "ground_balls": 1,
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
        "clutch": 1,
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
    def rate_player(skills: PlayerSkills, throws: str = "R") -> RatingMap:
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
        if throws not in VALID_THROWS:
            raise ValueError(f"Invalid throws: {throws}")
        ratings = {}

        for role, weights in ROLE_WEIGHTS.items():
            ratings[role] = PlayerEvaluator._calculate_weighted_rating(skills, weights)

        if throws == "L":
            for pos in LEFT_HAND_CAPPED_POSITIONS:
                if pos in ratings:
                    ratings[pos] = min(ratings[pos], LEFT_HAND_CAP)

        # --- Overall Player (offense + arm + speed + best defense) ---
        defensive_value = max(
            ratings[pos] for pos in ["cf", "rf", "lf", "c", "1b", "2b", "ss", "3b"]
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

        ratings["prospect"] = PlayerEvaluator.prospect_rating(skills)

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

    @staticmethod
    def prospect_rating(skills: PlayerSkills) -> int:
        """
        Rate a player's value as a draft prospect.

        Weights raw, physical tools heavily since they are predictive
        of future ceiling. Coachable skills (accuracy, infield, outfield)
        will improve naturally and are less informative at draft time.
        """

        # Raw stuff and durability — accuracy is coachable so weighted low
        p_score = (
            skills["strikes"] * 0.40
            + skills["stamina"] * 0.25
            + skills["recovery"] * 0.20
            + skills["accuracy"] * 0.10
            + skills["clutch"] * 0.05
        )

        defensive = max(skills["infield"], skills["outfield"], skills["catching"])
        # Physical tools — defense skills are coachable so weighted low
        b_score = (
            skills["speed"] * 0.19
            + skills["power"] * 0.18
            + skills["arm"] * 0.11
            + skills["eye"] * 0.14
            + skills["contact"] * 0.16
            + skills["clutch"] * 0.08
            + skills["base_running"] * 0.05
            + defensive * 0.05
            + skills["durability"] * 0.04
        )

        return max(0, min(100, int(round(max(p_score, b_score)))))


# Call at module load time
PlayerEvaluator.validate_weights()
