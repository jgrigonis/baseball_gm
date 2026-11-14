# src/league/personas.py
"""
GM personas (plans/ai-gm-strategy.md, section 6): who an AI GM is. A persona
is a name, a one-line bio, an archetype and ten trait dials from 0 to 100,
where 50 is "as the game plays today". Personas live in a site-wide library
(gm_personas) and never change once created; only their chance of being
picked for a new league can.

This module is the pure part: the dials and how they read as words, the
archetypes the library is seeded from, and what the dials mean for an AI
team's tactics (its gm_profiles row), team state and trades.
src/api/services/personas.py picks and assigns them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.name_generator.names import NameGenerator
from src.team import manager_profile as mp

# (key, label, low end, high end, words for 0-19, 20-39, 40-59, 60-79, 80-100)
TRAITS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "stats_vs_scouting",
        "Stats vs scouting",
        "Trusts ratings",
        "Trusts results",
        (
            "trusts the scouts",
            "leans on the scouts",
            "weighs scouts and stats",
            "leans on the stats",
            "trusts the stats",
        ),
    ),
    (
        "time_horizon",
        "Time horizon",
        "Builds for later",
        "Wins now",
        (
            "builds for the long run",
            "patient",
            "balanced",
            "leans win-now",
            "wins now",
        ),
    ),
    (
        "risk",
        "Risk",
        "Cautious",
        "Gambler",
        ("very cautious", "cautious", "measured", "bold", "a gambler"),
    ),
    (
        "trade_activity",
        "Trading",
        "Rarely deals",
        "Always dealing",
        (
            "rarely deals",
            "deals now and then",
            "deals as often as most",
            "deals often",
            "always dealing",
        ),
    ),
    (
        "youth",
        "Youth vs veterans",
        "Plays veterans",
        "Plays kids",
        (
            "plays veterans",
            "leans on veterans",
            "mixes youth and experience",
            "leans on youth",
            "plays the kids",
        ),
    ),
    (
        "offense_defense",
        "Offense vs defense",
        "Glove first",
        "Bat first",
        ("glove first", "leans glove", "balanced", "leans bat", "bat first"),
    ),
    (
        "loyalty",
        "Loyalty",
        "Cuts bait fast",
        "Sticks with the core",
        (
            "cuts bait fast",
            "unsentimental",
            "fair",
            "loyal",
            "sticks with the core",
        ),
    ),
    (
        "small_ball",
        "Small ball",
        "Waits for the big inning",
        "Bunts and runs",
        (
            "waits for the big inning",
            "rarely bunts or runs",
            "picks spots to run",
            "bunts and runs",
            "small ball all day",
        ),
    ),
    (
        "bullpen_hook",
        "Bullpen hook",
        "Long leash",
        "Quick hook",
        (
            "long leash",
            "lets starters work",
            "normal hook",
            "quick hook",
            "very quick hook",
        ),
    ),
    (
        "analytics",
        "Analytics",
        "Old school",
        "Modern",
        (
            "old school",
            "traditional",
            "open-minded",
            "modern",
            "analytics-driven",
        ),
    ),
)
DIALS = tuple(t[0] for t in TRAITS)
NEUTRAL = dict.fromkeys(DIALS, 50)

# Chance of being picked for a new league: 0 never, 100 twice as likely as 50.
MAX_CHANCE = 100
DEFAULT_CHANCE = 50


def word(dial: str, value: int) -> str:
    """How a dial reads to players."""
    words = next(t[4] for t in TRAITS if t[0] == dial)
    return words[min(len(words) - 1, max(0, int(value)) // 20)]


def describe(dials: dict) -> list[dict]:
    """Each dial for a persona card: label, ends, value and words."""
    return [
        {
            "key": key,
            "label": label,
            "ends": (low, high),
            "value": int(dials.get(key, 50)),
            "word": word(key, dials.get(key, 50)),
        }
        for key, label, low, high, _ in TRAITS
    ]


def clean(dials: dict) -> dict[str, int]:
    """Every dial, as a whole number from 0 to 100 (50 if missing)."""
    out = {}
    for key in DIALS:
        try:
            v = int(round(float(dials.get(key, 50))))
        except TypeError, ValueError:
            v = 50
        out[key] = max(0, min(100, v))
    return out


# ── Archetypes ───────────────────────────────────────────────────────────────
# Each is spread into PER_ARCHETYPE personas, every dial moved by up to
# JITTER, with a random name.


@dataclass(frozen=True)
class Archetype:
    name: str
    bio: str
    dials: tuple[int, ...]  # in DIALS order


ARCHETYPES = (
    #                                     svs hor risk act youth o/d loy small hook anly
    Archetype(
        "The Old Scout",
        "Trusts the eye test and the radar gun over any box score.",
        (15, 50, 40, 40, 45, 40, 70, 60, 30, 15),
    ),
    Archetype(
        "The Spreadsheet",
        "Runs every decision through the numbers, twice.",
        (85, 50, 50, 60, 55, 60, 30, 15, 75, 92),
    ),
    Archetype(
        "The Gambler",
        "Never met a blockbuster they didn't like.",
        (55, 70, 92, 85, 50, 65, 30, 45, 55, 60),
    ),
    Archetype(
        "The Builder",
        "Grows a winner from the farm up, one draft at a time.",
        (50, 15, 35, 45, 85, 45, 65, 45, 50, 60),
    ),
    Archetype(
        "The Win-Now Hire",
        "Brought in to win this year, and knows it.",
        (45, 92, 70, 75, 15, 65, 40, 40, 60, 45),
    ),
    Archetype(
        "Small-Ball Sam",
        "Bunts, steals and hit-and-runs, inning after inning.",
        (40, 55, 45, 45, 50, 25, 60, 92, 50, 25),
    ),
    Archetype(
        "The Loyalist",
        "Sticks with the core through thick and thin.",
        (35, 45, 25, 20, 40, 50, 92, 50, 35, 40),
    ),
    Archetype(
        "The Wheeler-Dealer",
        "Always on the phone, always working an angle.",
        (50, 60, 65, 95, 50, 50, 10, 50, 50, 55),
    ),
    Archetype(
        "The Pitching Guru",
        "Builds from the mound out and never lets a tired arm hang.",
        (50, 50, 40, 45, 50, 20, 55, 55, 85, 65),
    ),
    Archetype(
        "The Bomber",
        "Wants a lineup that can hit it out from one to nine.",
        (55, 65, 60, 55, 45, 92, 45, 8, 35, 60),
    ),
    Archetype(
        "The Caretaker",
        "Steady hands, no surprises, no big swings.",
        (50, 40, 15, 25, 50, 50, 70, 50, 50, 50),
    ),
    Archetype(
        "The Kid Whisperer",
        "Would rather play a 21-year-old than a 31-year-old any day.",
        (60, 25, 60, 55, 95, 55, 40, 55, 60, 70),
    ),
    Archetype(
        "The Glove Snob",
        "Defense wins championships, and nobody can say otherwise.",
        (35, 50, 35, 40, 50, 8, 60, 70, 40, 35),
    ),
)
PER_ARCHETYPE = 8
JITTER = 8
SEED = 2026


def seed(rng: random.Random | None = None) -> list[dict]:
    """The starting library: PER_ARCHETYPE personas from each archetype, each
    with jittered dials and a random name, all at DEFAULT_CHANCE."""
    rng = rng or random.Random(SEED)
    names = NameGenerator(rng=rng)
    used: set[str] = set()
    out = []
    for arch in ARCHETYPES:
        for _ in range(PER_ARCHETYPE):
            name = ""
            while not name or name in used:
                first, last = names.full("either")
                name = f"{first.title()} {last.title()}"
            used.add(name)
            dials = {
                k: max(0, min(100, v + rng.randint(-JITTER, JITTER)))
                for k, v in zip(DIALS, arch.dials)
            }
            out.append(
                {
                    "name": name,
                    "bio": arch.bio,
                    "archetype": arch.name,
                    "dials": dials,
                    "chance": DEFAULT_CHANCE,
                }
            )
    return out


# ── What the dials do ────────────────────────────────────────────────────────


def _band(value: int, low: int = 34, high: int = 67) -> int:
    """0 below low, 2 at or above high, else 1."""
    return 0 if value < low else 2 if value >= high else 1


def profile(dials: dict) -> dict:
    """The gm_profiles settings an AI team with these dials plays by. The
    tactical dials (small ball, bullpen hook, analytics, loyalty, time
    horizon) pick the Strategy tab settings a person would."""
    d = clean(dials)
    small, hook, modern = d["small_ball"], d["bullpen_hook"], d["analytics"]
    loyal, now = d["loyalty"], d["time_horizon"]

    if d["offense_defense"] >= 80 and small < 30:
        style = "power-first"
    elif d["offense_defense"] <= 20:
        style = "defensive"
    elif small >= 80:
        style = "speed-first"
    elif modern < 34:
        style = "traditional"
    else:
        style = "analytics"

    if modern >= 80 and loyal < 34:
        platoon = "aggressive"
    elif modern < 34 or loyal >= 67:
        platoon = "none"
    else:
        platoon = "vs-handedness"

    if hook < 15:
        starter = "105"
    elif hook < 34:
        starter = "95"
    elif hook >= 67 and modern >= 50:
        starter = "75"
    else:
        starter = "85"

    return {
        "lineup_style": style,
        "baserunning": mp.BASERUNNING[min(4, small // 20)],
        "sac_bunt": mp.SAC_BUNT[_band(small, 30, 71)],
        "starter_usage": starter,
        "closer_usage": mp.CLOSER_USAGE[_band(modern, 60, 85)],
        "bullpen_pref": mp.BULLPEN_PREF[_band(hook)],
        "platoon_usage": platoon,
        "rotation_size": 5,
        "skip_fifth_starter": now >= 75,
        "playoff_rotation": "3" if now >= 85 else "4" if now >= 65 else "same",
        "tired_starters": mp.TIRED_STARTERS[_band(hook)],
        "rest_days": "iron-man" if loyal >= 85 else "standard",
        "stats_vs_scouting": d["stats_vs_scouting"],
    }


@dataclass(frozen=True)
class Leanings:
    """What a GM's persona means for front-office decisions. A person's team
    is neutral except for their stats-vs-scouting setting."""

    time_horizon: int = 50
    risk: int = 50
    trade_activity: int = 50
    stats_vs_scouting: int = 50
    youth: int = 50
    offense_defense: int = 50

    @classmethod
    def from_dials(cls, dials: dict | None) -> Leanings:
        d = clean(dials or {})
        return cls(**{f: d[f] for f in cls.__dataclass_fields__})

    @property
    def lean(self) -> float:
        """-1 (patient) to 1 (win now): moves team state thresholds. Mostly
        the time horizon, a little the risk appetite."""
        return 0.7 * (self.time_horizon - 50) / 50 + 0.3 * (self.risk - 50) / 50

    @property
    def horizon(self) -> float:
        """-1 (builds for later) to 1 (wins now): the trade now/future blend."""
        return (self.time_horizon - 50) / 50

    @property
    def margin_factor(self) -> float:
        """Multiplies the share of what it gives up a GM wants to win a trade
        by: 1.5 for the most cautious, 0.5 for a gambler."""
        return 1.5 - self.risk / 100

    @property
    def activity_factor(self) -> float:
        """Multiplies how often a GM looks for a trade: 0.5 to 1.5."""
        return 0.5 + self.trade_activity / 100

    @property
    def stats_weight(self) -> float:
        return self.stats_vs_scouting / 100


def choose(pool: list[dict], taken: set[str], rng: random.Random) -> dict | None:
    """A persona from pool ({id, chance, ...}), weighted by chance, leaving
    out those in taken. Chance 0 is never picked. When every pickable persona
    is taken, repeats are allowed. None if nothing is pickable."""
    pickable = [p for p in pool if p["chance"] > 0]
    fresh = [p for p in pickable if p["id"] not in taken] or pickable
    if not fresh:
        return None
    return rng.choices(fresh, weights=[p["chance"] for p in fresh])[0]
