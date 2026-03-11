# src/player/fatigue.py

from dataclasses import dataclass

from src.player.fatigue_level import FatigueLevel

@dataclass
class PitcherFatigue:
    """Track pitcher fatigue state."""

    pitches_thrown: int = 0
    batters_faced: int = 0
    energy: float = 1.0  # 1.0 = fresh, 0.0 = exhausted

    # Energy thresholds
    FRESH_THRESHOLD = 0.85
    GOOD_THRESHOLD = 0.65
    TIRED_THRESHOLD = 0.40
    EXHAUSTED_THRESHOLD = 0.01

    # stamina rating
    stamina: int = 50

    def __post_init__(self):
        """Validate stamina is positive."""
        if self.stamina <= 0:
            raise ValueError(f"Stamina must be positive, got {self.stamina}")

    def get_level(self) -> FatigueLevel:
        """Determine current fatigue level."""
        if self.energy >= self.FRESH_THRESHOLD:
            return FatigueLevel.FRESH
        elif self.energy >= self.GOOD_THRESHOLD:
            return FatigueLevel.GOOD
        elif self.energy >= self.TIRED_THRESHOLD:
            return FatigueLevel.TIRED
        elif self.energy >= self.EXHAUSTED_THRESHOLD:
            return FatigueLevel.EXHAUSTED
        return FatigueLevel.ZERO

    def add_pitch(self, pitch_type: str = "fastball") -> None:
        """Record a pitch and decrease energy."""
        self.pitches_thrown += 1

        # Different pitch types drain energy differently
        drain_rates = {
            "fastball": 0.01,
            # "curveball": 0.005,
            # "slider": 0.004,
            # "changeup": 0.003,
            # "knuckleball": 0.002,
        }

        drain = drain_rates.get(pitch_type, 0.01)
        drain *= 50 / self.stamina
        self.energy = max(0.0, self.energy - drain)

    def add_batter(self) -> None:
        """Record facing a batter."""
        self.batters_faced += 1

    def get_stat_modifier(self) -> float:
        """
        Get performance modifier based on fatigue.
        Returns multiplier for pitcher stats (1.0 = no effect, <1.0 = worse).
        """
        level = self.get_level()

        modifiers = {
            FatigueLevel.FRESH: 1.05,  # Slight bonus when fresh
            FatigueLevel.GOOD: 1.0,  # No effect
            FatigueLevel.TIRED: 0.90,  # 10% worse
            FatigueLevel.EXHAUSTED: 0.75,  # 25% worse
            FatigueLevel.ZERO: 0.50,  # 50% worse
        }

        return modifiers[level]

    def set_energy(self, level):
        self.energy = max(0, min(1, level))
