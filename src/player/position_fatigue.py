# src/player/position_fatigue.py

from dataclasses import dataclass, field
from enum import Enum

from src.db.repositories.player_energy import _daily_recovery_rate


class FatigueLevel(Enum):
    FRESH = "fresh"
    GOOD = "good"
    TIRED = "tired"
    EXHAUSTED = "exhausted"
    ZERO = "ZERO"


# Catchers drain fastest, middle infielders moderate, corners/OF lightest
POSITION_DRAIN_RATES = {
    "C": 0.055,
    "SS": 0.038,
    "2B": 0.035,
    "3B": 0.028,
    "CF": 0.028,
    "1B": 0.022,
    "LF": 0.020,
    "RF": 0.020,
    "DH": 0.010,
}

# How much energy is recovered per rest day
REST_RECOVERY_RATE = 0.30


@dataclass
class PositionPlayerFatigue:
    """
    Track fatigue state for a position player across games.

    Energy drains per game based on position and playing time,
    and recovers on rest days. Designed for multi-season use:
    call end_season() during the offseason for a full reset.
    """

    position: str = "LF"
    energy: float = 1.0  # 1.0 = fresh, 0.0 = exhausted
    max_energy: float = 1.0
    durability: int = 50  # Player attribute, like stamina for pitchers

    # In-season tracking
    consecutive_days: int = 0  # Streak of days in lineup without a break
    season_games_played: int = 0

    # Energy thresholds (mirrors PitcherFatigue)
    FRESH_THRESHOLD: float = field(default=0.85, init=False, repr=False)
    GOOD_THRESHOLD: float = field(default=0.65, init=False, repr=False)
    TIRED_THRESHOLD: float = field(default=0.40, init=False, repr=False)
    EXHAUSTED_THRESHOLD: float = field(default=0.01, init=False, repr=False)

    def __post_init__(self):
        if self.durability <= 0:
            raise ValueError(f"Durability must be positive, got {self.durability}")
        if self.position not in POSITION_DRAIN_RATES:
            raise ValueError(
                f"Unknown position '{self.position}'. Valid: {list(POSITION_DRAIN_RATES)}"
            )

    # ------------------------------------------------------------------
    # Core state
    # ------------------------------------------------------------------

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

    def get_stat_modifier(self) -> float:
        """
        Performance multiplier based on fatigue level.
        Mirrors PitcherFatigue.get_stat_modifier().
        """
        modifiers = {
            FatigueLevel.FRESH: 1.03,  # Small bonus when fresh
            FatigueLevel.GOOD: 1.0,
            FatigueLevel.TIRED: 0.92,  # 8% worse
            FatigueLevel.EXHAUSTED: 0.80,  # 20% worse
            FatigueLevel.ZERO: 0.60,  # 40% worse
        }
        return modifiers[self.get_level()]

    # ------------------------------------------------------------------
    # Game events
    # ------------------------------------------------------------------

    # was play_game
    # Only used in unit tests
    def record_game(self, innings_played: int = 9) -> None:
        """
        Record a game played. Drain scales with innings and position.

        Args:
            innings_played: Partial games (e.g. pinch hitting = 1) drain less.
        """
        base_drain = POSITION_DRAIN_RATES[self.position]

        # Scale by innings share (9 = full game)
        innings_fraction = min(innings_played, 9) / 9.0

        # Durability reduces drain, same pattern as pitcher stamina
        drain = base_drain * innings_fraction * (50 / self.durability)

        # Consecutive day penalty: each day in a long streak adds a small
        # extra drain (fatigue compounds — day 7+ hurts more than day 2)
        streak_penalty = max(0, (self.consecutive_days - 4) * 0.005)
        drain += streak_penalty

        self.energy = max(0.0, self.energy - drain)
        self.consecutive_days += 1
        self.season_games_played += 1
        self.degrade_cap()

    def degrade_cap(self) -> None:
        """Degrade seasonal ceiling based on accumulated workload."""
        # Only starts biting after 100 games
        if self.season_games_played < 100:
            return
        excess = self.season_games_played - 100
        # Light damage 100-140 games, heavier above 140
        if self.season_games_played < 140:
            damage = excess * 0.0004 * (50 / self.durability)
        else:
            damage = excess * 0.0008 * (50 / self.durability)
        self.max_energy = max(0.50, self.max_energy - damage)

    def rest_day(self, days: int = 1) -> None:
        """
        Recover energy on a day off. Consecutive rest days recover less
        (diminishing returns — first day of rest does the most work).
        Exponential recovery toward max_energy (not 1.0).
        """
        rate = _daily_recovery_rate(self.durability)
        for _ in range(days):
            self.energy += (self.max_energy - self.energy) * rate
        self.energy = max(0.0, min(self.max_energy, self.energy))
        self.consecutive_days = 0

    def end_season(self) -> None:
        """Full reset at the start of the offseason."""
        self.energy = 1.0
        self.consecutive_days = 0
        self.season_games_played = 0

    # ------------------------------------------------------------------
    # Injury risk (to wire up to your injury system later)
    # ------------------------------------------------------------------

    def get_injury_risk_multiplier(self) -> float:
        """
        Returns a multiplier for injury probability based on current fatigue.
        1.0 = baseline risk, higher = more likely to get hurt.

        Plug this into your injury roll:
            actual_risk = base_position_risk * fatigue.get_injury_risk_multiplier()
        """
        level = self.get_level()
        multipliers = {
            FatigueLevel.FRESH: 0.80,  # Slightly protected
            FatigueLevel.GOOD: 1.0,
            FatigueLevel.TIRED: 1.40,
            FatigueLevel.EXHAUSTED: 2.00,
            FatigueLevel.ZERO: 3.00,
        }
        return multipliers[level]

    def set_position_energy(self, level: float, max_level: float = 1.0) -> None:
        """Directly set energy (e.g. for testing or IL return)."""
        self.energy = max(0.0, min(max_level, level))
        self.max_energy = max_level
