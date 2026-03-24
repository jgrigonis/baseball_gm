from dataclasses import dataclass
from src.player.fatigue_level import FatigueLevel


def _cap_damage_threshold(stamina: int) -> int:
    return 20 + (stamina // 5)  # ST=50 → 30, ST=100 → 40


def _cap_damage_heavy(stamina: int) -> int:
    return _cap_damage_threshold(stamina) + 30


@dataclass
class PitcherFatigue:
    """Track pitcher fatigue state."""

    pitches_thrown: int = 0
    batters_faced: int = 0
    energy: float = 1.0
    max_energy: float = 1.0
    stamina: int = 50

    FRESH_THRESHOLD = 0.85
    GOOD_THRESHOLD = 0.65
    TIRED_THRESHOLD = 0.40
    EXHAUSTED_THRESHOLD = 0.01

    MOD_FRESH = 1.05
    MOD_GOOD = 1.0
    MOD_TIRED = 0.9
    MOD_EXHAUSTED = 0.75
    MOD_ZERO = 0.5

    def __post_init__(self):
        if self.stamina <= 0:
            raise ValueError(f"Stamina must be positive, got {self.stamina}")

    # --- existing methods unchanged ---

    def get_level(self) -> FatigueLevel:
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
        self.pitches_thrown += 1
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
        self.batters_faced += 1

    def get_stat_modifier(self) -> float:
        modifiers = {
            FatigueLevel.FRESH: self.MOD_FRESH,
            FatigueLevel.GOOD: self.MOD_GOOD,
            FatigueLevel.TIRED: self.MOD_TIRED,
            FatigueLevel.EXHAUSTED: self.MOD_EXHAUSTED,
            FatigueLevel.ZERO: self.MOD_ZERO,
        }
        return modifiers[self.get_level()]

    def set_energy(self, level: float) -> None:
        self.energy = max(0.0, min(self.max_energy, level))

    # --- new post-outing methods ---

    def degrade_cap(self, pitch_count: int) -> None:
        """Degrade seasonal energy ceiling after a heavy outing."""
        threshold = _cap_damage_threshold(self.stamina)
        heavy = _cap_damage_heavy(self.stamina)

        if pitch_count < threshold:
            return

        if pitch_count < heavy:
            excess = pitch_count - threshold
            base_damage = excess * 0.0008
        else:
            excess = pitch_count - threshold
            base_damage = excess * 0.0018

        stamina_factor = 1.0 - (self.stamina / 100) * 0.5
        damage = base_damage * stamina_factor
        self.max_energy = max(0.25, self.max_energy - damage)
