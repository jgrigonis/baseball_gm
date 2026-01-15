# src/game/defense/resolver.py

"""
TODO:
Position-specific curves (SS vs 1B)
Double-play pivot difficulty
Throw strength vs runner speed
Catcher framing / passed balls

All live naturally in this class.
"""

from typing import Optional

from src.game.defense.outcome import DefenseOutcome


class DefensiveResolver:
    """
    Encapsulates all defensive play resolution logic.

    Returns:
        (success: bool, error_type: Optional[str])
            error_type ∈ {"error", "slow", None}
    """

    def __init__(self, rng, logger):
        self.rng = rng
        self.logger = logger

    def check_play(self, defender, play_type="fielding", position=None):
        """
        :param defender: Player making the play (may be None)
        :param play_type: "fielding", "speed", or "both" (could add arm here)
        :param position: "ss", "2b", "cf", etc.
        """
        if defender is None:
            return DefenseOutcome.fielding_error()

        pos = position.lower() if position else None
        skill = self._resolve_defensive_skill(defender, pos)

        # ----- Fielding check -----
        if play_type in ("fielding", "both"):
            if self.rng.random() < self._error_rate(skill):
                defender.game_stats.fielding.error()
                return DefenseOutcome.fielding_error()

        # ----- Speed check -----
        if play_type in ("speed", "both"):
            speed = defender.skills.get("speed", 50)
            if self.rng.random() < self._slow_rate(speed):
                return DefenseOutcome.too_slow()

        return DefenseOutcome.clean_play()

    # ----------------------------
    # Skill resolution helpers
    # ----------------------------

    def _resolve_defensive_skill(self, defender, position: Optional[str]) -> int:
        """
        Pick the correct defensive skill based on position.

        TODO: We left out pitchers here
        """
        if position == "c":
            return defender.skills.get("catching", 50)

        if position in ("1b", "2b", "3b", "ss"):
            return defender.skills.get("infield", 50)

        if position in ("lf", "cf", "rf"):
            return defender.skills.get("outfield", 50)

        # Fallback: position rating > infield > 50
        if position and position in defender.ratings:
            return defender.ratings.get(position, 50)

        return defender.skills.get("infield", 50)

    # ----------------------------
    # Probability curves
    # ----------------------------

    @staticmethod
    def _error_rate(skill: int) -> float:
        """
        Map defensive skill (0 - 100) → error probability.

        100 → ~0.5%
        50  → ~5%
        0   → ~15%
        """
        return max(0.005, 0.15 - (skill / 100.0) * 0.145)

    @staticmethod
    def _slow_rate(speed: int) -> float:
        """
        Map speed (0 - 100) → 'too slow' probability.

        100 → ~1%
        50  → ~5%
        0   → ~15%
        """
        return max(0.01, 0.15 - (speed / 100.0) * 0.14)
