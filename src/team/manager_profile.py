# src/team/manager_profile.py
"""
How a team is managed in games: the Strategy tab's settings, read by the game
engine. A person's team uses what they set; an AI team uses its own row
(set from its persona, src/league/personas.py). Every team has a gm_profiles row.

The middle (default) value of each setting reproduces how the engine played
before these settings existed, except rest days, which are new. Each
multiplier below is 1.0 at the default, so a default profile changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.db.repositories.pitcher_state import MIN_ENERGY_STARTER

BASERUNNING = (
    "very-conservative",
    "conservative",
    "standard",
    "aggressive",
    "very-aggressive",
)
SAC_BUNT = ("never", "situational", "frequent")
STARTER_USAGE = ("let-them-work", "pitch-count-strict", "matchup-based")
CLOSER_USAGE = ("saves-only", "high-leverage", "best-available")
BULLPEN_PREF = ("deep-pen", "starter-heavy")
PLATOON_USAGE = ("none", "vs-handedness", "aggressive")
LINEUP_STYLE = ("traditional", "analytics", "speed-first", "power-first")
ROTATION_SIZE = (4, 5, 6)
PLAYOFF_ROTATION = ("3", "4", "same")
TIRED_STARTERS = ("push", "standard", "protect")
REST_DAYS = ("iron-man", "standard", "rest-often")
STATS_VS_SCOUTING = (0, 25, 50, 75, 100)

# Baserunning: how often runners steal (and hit and run), and how often they
# try for the extra base on a hit. Extra-base tries beyond the standard
# rate can be thrown out.
STEAL_FACTOR = dict(zip(BASERUNNING, (0.4, 0.7, 1.0, 1.35, 1.75)))
EXTRA_BASE_FACTOR = dict(zip(BASERUNNING, (0.8, 0.9, 1.0, 1.1, 1.2)))

BUNT_FACTOR = {"never": 0.0, "situational": 1.0, "frequent": 2.0}

# Starter leash: extra pitches allowed past the pitch-count threshold, and a
# multiplier on the chance of pulling him.
PITCH_COUNT_OFFSET = {"let-them-work": 15, "pitch-count-strict": 0, "matchup-based": 0}
STARTER_HOOK = {"let-them-work": 0.7, "pitch-count-strict": 1.0, "matchup-based": 1.0}
# Matchup-based managers pull a starter sooner the third time through the order.
THIRD_TIME_BATTERS = 18
THIRD_TIME_HOOK = 1.5
STARTER_HEAVY_HOOK = 0.8

# The energy a scheduled starter needs, or the next man up takes the game.
STARTER_MIN_ENERGY = {"push": 0.75, "standard": MIN_ENERGY_STARTER, "protect": 0.9}

# A regular sits when his energy is below this. Catchers sit a little sooner.
REST_ENERGY = {"iron-man": 0.0, "standard": 0.4, "rest-often": 0.6}
CATCHER_REST_BONUS = 0.1


@dataclass(frozen=True)
class ManagerProfile:
    lineup_style: str = "analytics"
    baserunning: str = "standard"
    sac_bunt: str = "situational"
    starter_usage: str = "pitch-count-strict"
    closer_usage: str = "saves-only"
    bullpen_pref: str = "deep-pen"
    platoon_usage: str = "none"
    rotation_size: int = 5
    skip_fifth_starter: bool = False
    playoff_rotation: str = "same"
    tired_starters: str = "standard"
    rest_days: str = "standard"
    # How much a player's season stats count against his ratings, 0 to 100
    # (src/league/performance.py). 50 weighs them equally.
    stats_vs_scouting: int = 50

    @classmethod
    def from_row(cls, row: dict | None) -> ManagerProfile:
        """A profile from a gm_profiles row; anything missing or unknown keeps
        its default."""
        if not row:
            return cls()
        allowed = {
            "lineup_style": LINEUP_STYLE,
            "baserunning": BASERUNNING,
            "sac_bunt": SAC_BUNT,
            "starter_usage": STARTER_USAGE,
            "closer_usage": CLOSER_USAGE,
            "bullpen_pref": BULLPEN_PREF,
            "platoon_usage": PLATOON_USAGE,
            "rotation_size": ROTATION_SIZE,
            "playoff_rotation": PLAYOFF_ROTATION,
            "tired_starters": TIRED_STARTERS,
            "rest_days": REST_DAYS,
        }
        values = {k: row[k] for k, ok in allowed.items() if row.get(k) in ok}
        if row.get("skip_fifth_starter") is not None:
            values["skip_fifth_starter"] = bool(row["skip_fifth_starter"])
        stats = row.get("stats_vs_scouting")
        if isinstance(stats, int) and 0 <= stats <= 100:
            values["stats_vs_scouting"] = stats
        return cls(**values)

    @property
    def stats_weight(self) -> float:
        """The share of a player's value that comes from his stats."""
        return self.stats_vs_scouting / 100

    @property
    def steal_factor(self) -> float:
        return STEAL_FACTOR[self.baserunning]

    @property
    def extra_base_factor(self) -> float:
        return EXTRA_BASE_FACTOR[self.baserunning]

    @property
    def bunt_factor(self) -> float:
        return BUNT_FACTOR[self.sac_bunt]

    @property
    def pitch_count_offset(self) -> int:
        return PITCH_COUNT_OFFSET[self.starter_usage]

    def starter_hook(self, batters_faced: int) -> float:
        """Multiplier on the chance of pulling a starter."""
        hook = STARTER_HOOK[self.starter_usage]
        if (
            self.starter_usage == "matchup-based"
            and batters_faced >= THIRD_TIME_BATTERS
        ):
            hook *= THIRD_TIME_HOOK
        if self.bullpen_pref == "starter-heavy":
            hook *= STARTER_HEAVY_HOOK
        return hook

    @property
    def starter_min_energy(self) -> float:
        return STARTER_MIN_ENERGY[self.tired_starters]

    @property
    def playoff_rotation_size(self) -> int | None:
        """How many starters cycle in the playoffs; None for the whole rotation."""
        return None if self.playoff_rotation == "same" else int(self.playoff_rotation)

    def rest_energy(self, position: str) -> float:
        """Below this energy, a regular at this position gets the day off."""
        threshold = REST_ENERGY[self.rest_days]
        if threshold and position == "c":
            threshold += CATCHER_REST_BONUS
        return threshold


DEFAULT_PROFILE = ManagerProfile()


def profile_of(team) -> ManagerProfile:
    """The team's profile, or the default for a team without one."""
    profile = getattr(team, "profile", None)
    return profile if isinstance(profile, ManagerProfile) else DEFAULT_PROFILE
