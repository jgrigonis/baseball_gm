# src/player/fatigue.py
from dataclasses import dataclass

from src.player.fatigue_level import FatigueLevel
from src.player.player_constants import (
    FRESH_THRESHOLD,
    GOOD_THRESHOLD,
    TIRED_THRESHOLD,
    EXHAUSTED_THRESHOLD,
    MOD_FRESH,
    MOD_GOOD,
    MOD_TIRED,
    MOD_EXHAUSTED,
    MOD_ZERO,
    FASTBALL_DRAIN,
    CAP_DMG_LOW,
    CAP_DMG_HIGH,
)


def _cap_damage_threshold(stamina: int) -> int:
    """
    Higher stamina gives a higher floor of pitches allowed
    before the damage kicks in.

    ST=50 → 45 pitch floor, ST=100 → 70 pitch floor

    """
    return 20 + stamina // 2


def _cap_damage_heavy(stamina: int) -> int:
    """
    The heavy threshold is just 30 pitches over the
    above calculation

    This seems fine for now, adjust second

    """
    return _cap_damage_threshold(stamina) + 30


@dataclass
class PitcherFatigue:
    """Track pitcher fatigue state."""

    pitches_thrown: int = 0
    batters_faced: int = 0
    energy: float = 1.0
    max_energy: float = 1.0
    stamina: int = 50

    def __post_init__(self):
        if self.stamina <= 0:
            raise ValueError(f"Stamina must be positive, got {self.stamina}")

    # --- existing methods unchanged ---

    def get_level(self) -> FatigueLevel:
        if self.energy >= FRESH_THRESHOLD:
            return FatigueLevel.FRESH
        elif self.energy >= GOOD_THRESHOLD:
            return FatigueLevel.GOOD
        elif self.energy >= TIRED_THRESHOLD:
            return FatigueLevel.TIRED
        elif self.energy >= EXHAUSTED_THRESHOLD:
            return FatigueLevel.EXHAUSTED
        return FatigueLevel.ZERO

    def add_pitch(self, pitch_type: str = "fastball") -> None:
        self.pitches_thrown += 1
        drain_rates = {
            "fastball": FASTBALL_DRAIN,
            # "curveball": 0.005,
            # "slider": 0.004,
            # "changeup": 0.003,
            # "knuckleball": 0.002,
        }
        drain = drain_rates.get(pitch_type, FASTBALL_DRAIN)
        drain *= 50 / self.stamina
        self.energy = max(0.0, self.energy - drain)

    # This is never called anywhere
    def add_batter(self) -> None:
        self.batters_faced += 1

    def get_stat_modifier(self) -> float:
        modifiers = {
            FatigueLevel.FRESH: MOD_FRESH,
            FatigueLevel.GOOD: MOD_GOOD,
            FatigueLevel.TIRED: MOD_TIRED,
            FatigueLevel.EXHAUSTED: MOD_EXHAUSTED,
            FatigueLevel.ZERO: MOD_ZERO,
        }
        return modifiers[self.get_level()]

    def set_energy(self, level: float, max_level: float) -> None:
        self.energy = max(0.0, min(max_level, level))
        self.max_energy = max_level

    # --- new post-outing methods ---

    def degrade_cap(self, pitch_count: int) -> None:
        """Degrade seasonal energy ceiling after a heavy outing."""
        threshold = _cap_damage_threshold(self.stamina)
        heavy = _cap_damage_heavy(self.stamina)

        if pitch_count < threshold:
            return

        if pitch_count < heavy:
            excess = pitch_count - threshold
            base_damage = excess * CAP_DMG_LOW
        else:
            base_damage = (heavy - threshold) * CAP_DMG_LOW
            heavy_excess = pitch_count - heavy
            base_damage += heavy_excess * CAP_DMG_HIGH

        # 100 stamina = 0.500 stamina_factor
        #  75 stamina = 0.625 stamina_factor
        #  50 stamina = 0.750 stamina_factor
        #  25 stamina = 0.875 stamina_factor
        # Lower stamina, higher damage
        stamina_factor = 1.0 - (self.stamina / 100) * 0.5
        damage = base_damage * stamina_factor
        self.max_energy = max(0.25, self.max_energy - damage)
