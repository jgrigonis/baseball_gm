# src/team/manager_profile.py
"""
How a team is managed in games: the Strategy tab's settings, read by the game
engine. A person's team uses what they set; an AI team uses its own row
(set from its persona, src/league/personas.py). Every team has a gm_profiles row.

The middle (default) value of each setting reproduces how the engine played
before these settings existed, except rest days, which are new, and
platoons, which default to vs-handedness (the middle setting). Each
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
# Starter Leash: the pitch count a starter is usually pulled at, longest
# first (Josh, 2026-11-13: 75 to 115 in steps of 10; 2026-11-14: 85 the
# default, close to the old standard target of 88).
STARTER_USAGE = ("115", "105", "95", "85", "75")
DEFAULT_LEASH = "85"
CLOSER_USAGE = ("saves-only", "high-leverage", "best-available")
BULLPEN_PREF = ("starter-heavy", "balanced", "deep-pen")
PLATOON_USAGE = ("none", "vs-handedness", "aggressive")
LINEUP_STYLE = ("traditional", "analytics", "speed-first", "power-first", "defensive")
ROTATION_SIZE = (4, 5, 6)
PLAYOFF_ROTATION = ("3", "4", "same")
TIRED_STARTERS = ("push", "standard", "protect")
REST_DAYS = ("iron-man", "standard", "rest-often")
STATS_VS_SCOUTING = (0, 25, 50, 75, 100)
# Lineup updates: play the saved batting orders as they are, or rebuild and
# save them before every game (src/league/injury_lineup.py).
LINEUP_UPDATES = ("keep", "daily")
# Injury lineup: auto-fill outs up to this many days, rebuild longer ones.
INJURY_FILL_DAYS = (10, 7, 5, 3, 2, 1)
INJURY_LINEUP = ("fill", *(f"fill-{d}" for d in INJURY_FILL_DAYS), "rebuild")
# A hitter out longer than this many days gets the batting orders rebuilt
# (src/league/injury_lineup.py); None never rebuilds.
REBUILD_AFTER_DAYS = {
    "fill": None,
    **{f"fill-{d}": d for d in INJURY_FILL_DAYS},
    "rebuild": 0,
}

# Baserunning: how often runners steal (and hit and run), and how often they
# try for the extra base on a hit. Extra-base tries beyond the standard
# rate can be thrown out.
STEAL_FACTOR = dict(zip(BASERUNNING, (0.4, 0.7, 1.0, 1.35, 1.75)))
EXTRA_BASE_FACTOR = dict(zip(BASERUNNING, (0.8, 0.9, 1.0, 1.1, 1.2)))

BUNT_FACTOR = {"never": 0.0, "situational": 1.0, "frequent": 2.0}

# The short leash (75) also pulls a starter sooner the third time through
# the order.
SHORT_LEASHES = ("75",)
THIRD_TIME_BATTERS = 18
THIRD_TIME_HOOK = 1.5

# Bullpen shape: how a manager reacts to trouble and uses his relievers.
# TROUBLE_HOOK multiplies the chance of pulling a starter before he reaches
# his pitch count, which is mostly a starter who's getting hit.
TROUBLE_HOOK = {"starter-heavy": 0.3, "balanced": 1.0, "deep-pen": 1.6}
# The least chance of pulling a starter who has reached his pitch count, at
# each check: a starter-heavy manager lets him finish a few more batters.
AT_TARGET_PULL = {"starter-heavy": 0.45, "balanced": 0.72, "deep-pen": 0.72}
# The chance a reliever who has done his inning (two for a long man) sits
# before the next one starts.
RELIEVER_DONE = {"starter-heavy": 0.65, "balanced": 0.9, "deep-pen": 0.97}

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
    starter_usage: str = DEFAULT_LEASH
    closer_usage: str = "saves-only"
    bullpen_pref: str = "balanced"
    platoon_usage: str = "vs-handedness"
    rotation_size: int = 5
    skip_fifth_starter: bool = False
    playoff_rotation: str = "same"
    tired_starters: str = "standard"
    rest_days: str = "standard"
    # How much a player's season stats count against his ratings, 0 to 100
    # (src/league/performance.py). 50 weighs them equally.
    stats_vs_scouting: int = 50
    # Players still rusty from an injury sit until it fades: left out of
    # Rebuild and Auto-fill, given no bullpen role, and treated like the
    # injured on game day. Off plays them through it.
    rest_rusty: bool = False
    # What happens to a person's saved batting orders when a hitter is hurt:
    # auto-fill his slot for the day, or rebuild them for outs longer than
    # some number of days, or for any out (INJURY_LINEUP).
    injury_lineup: str = "fill"
    # Keep a person's saved batting orders, or rebuild them before every game,
    # changing them only when a change is clearly better (LINEUP_UPDATES).
    lineup_updates: str = "keep"

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
            "injury_lineup": INJURY_LINEUP,
            "lineup_updates": LINEUP_UPDATES,
        }
        values = {k: row[k] for k, ok in allowed.items() if row.get(k) in ok}
        if row.get("skip_fifth_starter") is not None:
            values["skip_fifth_starter"] = bool(row["skip_fifth_starter"])
        if row.get("rest_rusty") is not None:
            values["rest_rusty"] = bool(row["rest_rusty"])
        stats = row.get("stats_vs_scouting")
        if isinstance(stats, int) and 0 <= stats <= 100:
            values["stats_vs_scouting"] = stats
        return cls(**values)

    @property
    def stats_weight(self) -> float:
        """The share of a player's value that comes from his stats."""
        return self.stats_vs_scouting / 100

    @property
    def rebuild_after_days(self) -> int | None:
        """A hitter out longer than this many days gets the batting orders
        rebuilt; None never rebuilds."""
        return REBUILD_AFTER_DAYS[self.injury_lineup]

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
    def leash_pitches(self) -> int:
        """The pitch count his starters are usually pulled at."""
        return int(self.starter_usage)

    def starter_hook(self, batters_faced: int) -> float:
        """Multiplier on the chance of pulling a starter: a short leash pulls
        him sooner the third time through the order."""
        if self.starter_usage in SHORT_LEASHES and batters_faced >= THIRD_TIME_BATTERS:
            return THIRD_TIME_HOOK
        return 1.0

    @property
    def trouble_hook(self) -> float:
        """Multiplier on the chance of pulling a starter short of his pitch
        count."""
        return TROUBLE_HOOK[self.bullpen_pref]

    @property
    def at_target_pull(self) -> float:
        """Least chance of pulling a starter who has reached his pitch count."""
        return AT_TARGET_PULL[self.bullpen_pref]

    @property
    def reliever_done(self) -> float:
        """Chance a reliever who has done his inning sits before the next."""
        return RELIEVER_DONE[self.bullpen_pref]

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
