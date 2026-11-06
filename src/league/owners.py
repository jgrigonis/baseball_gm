# src/league/owners.py
"""
Team owners (plans/owners.md): every team's owner is the GM's boss. An owner
is a name, a one-line bio, an archetype ("The Showman"), a weight from 0 to
100 on each thing they judge a GM by, and a few trait dials that shape how
they behave. Owners live in a site-wide library (owner_personas), like GM
personas (src/league/personas.py), and never change once created; only
their chance of being drawn for a new team can.

The numbers are for admins. GMs see the owner's name, bio and archetype,
what owners of that archetype want in general terms, and (later) a mood
word and the owner's messages, never a weight or a dial.

This module is the pure part: the dimensions and traits, the archetypes the
library is seeded from, and the draw. src/api/services/owners.py gives each
team its owner.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.name_generator.names import NameGenerator

# ── What owners judge a GM by ────────────────────────────────────────────────
# (key, label, how it's measured). Each owner weighs every one from 0 (doesn't
# care) to 100 (what they care about most). Money is judged by profit alone
# (Josh, 2026-11-06): payroll past the budget costs the owner, and past their
# hard limit they refuse it (src/league/budget.py).
DIMENSIONS: tuple[tuple[str, str, str], ...] = (
    ("wins", "Winning", "Regular-season win % against the target"),
    ("postseason", "October", "Playoff appearances, rounds won and titles"),
    ("profit", "Profit", "Revenue minus payroll, luxury tax and costs"),
    ("attendance", "Attendance", "How full the ballpark is"),
    ("fans", "Fan interest", "Fan interest rising over the season"),
    ("future", "Future health", "The farm and the team's strength two years out"),
    ("homegrown", "Homegrown talent", "Value from players the team drafted"),
    ("stars", "Star power", "All-Stars, award winners and top players"),
    ("icons", "Franchise icons", "Keeping long-tenured, high-value players"),
    ("stability", "Stability", "Few trades and low roster turnover"),
    ("rivalry", "Rivalry", "The record against their rival"),
)
WEIGHTS = tuple(d[0] for d in DIMENSIONS)

# (key, label, low end, high end). Dials from 0 to 100 that shape how the
# owner behaves rather than what they want.
TRAITS: tuple[tuple[str, str, str, str], ...] = (
    ("patience", "Patience", "Hot seat after one bad year", "Gives a GM years"),
    ("ambition", "Ambition", "Happy with .500", "Expects to contend"),
    ("horizon", "Time horizon", "Judges the long run", "Judges this season"),
    ("meddling", "Meddling", "Leaves the GM alone", "Steps in"),
    ("temper", "Temper", "Steady", "Mood swings fast"),
    ("chattiness", "Chattiness", "Rarely writes", "Writes often"),
    ("spending", "Spending", "Miser", "Spends to win"),
)
TRAIT_KEYS = tuple(t[0] for t in TRAITS)

# Chance of being drawn for a team: 0 never, 100 twice as likely as 50.
MAX_CHANCE = 100
DEFAULT_CHANCE = 50

# A weight at or above this is something the owner is known for: it's what
# their messages talk about, and a rival is named on their card.
STRONG = 70


def _clean(values: dict, keys: tuple[str, ...]) -> dict[str, int]:
    out = {}
    for key in keys:
        try:
            v = int(round(float(values.get(key, 50))))
        except TypeError, ValueError:
            v = 50
        out[key] = max(0, min(100, v))
    return out


def clean_weights(weights: dict) -> dict[str, int]:
    """Every weight, as a whole number from 0 to 100 (50 if missing)."""
    return _clean(weights, WEIGHTS)


def clean_traits(traits: dict) -> dict[str, int]:
    """Every trait, as a whole number from 0 to 100 (50 if missing)."""
    return _clean(traits, TRAIT_KEYS)


def top_dimensions(weights: dict, n: int = 3) -> list[str]:
    """The keys of the n things an owner weighs most, heaviest first (ties
    in DIMENSIONS order)."""
    w = clean_weights(weights)
    return sorted(WEIGHTS, key=lambda k: -w[k])[:n]


# ── Archetypes ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Archetype:
    name: str
    bio: str
    # What owners of this kind want, in general terms. Public: GMs see it on
    # the owner card, so it never names a number.
    wants: str
    weights: tuple[int, ...]  # in WEIGHTS order
    traits: tuple[int, ...]  # in TRAIT_KEYS order
    # -1 to 1: how much more often a big market (positive) or a small one
    # (negative) draws this kind of owner.
    market_tilt: float = 0.0


ARCHETYPES = (
    #                 wins post prof att fans fut home star icon stab riv
    #                 pat amb hor med tem chat spend
    Archetype(
        "The Tycoon",
        "Money's no object. Rings are.",
        "Tycoon owners want titles and stars, and will pay for them.",
        (80, 95, 5, 30, 30, 20, 10, 60, 20, 20, 30),
        (20, 95, 85, 60, 70, 65, 95),
        1.0,
    ),
    Archetype(
        "The Penny-Pincher",
        "Every dollar counts, and they count them all.",
        "Penny-Pinchers want a profit, every season.",
        (35, 20, 95, 40, 20, 30, 30, 10, 20, 50, 10),
        (50, 30, 50, 70, 50, 60, 5),
        -1.0,
    ),
    Archetype(
        "The Hometown Owner",
        "Grew up in the bleachers. Loves the club's own.",
        "Hometown Owners want homegrown players and the club's icons kept.",
        (45, 40, 30, 50, 75, 40, 80, 30, 90, 60, 60),
        (70, 50, 40, 40, 40, 45, 50),
        -0.3,
    ),
    Archetype(
        "The Showman",
        "Wants a full park and names on the marquee.",
        "Showmen want stars and a full ballpark.",
        (50, 50, 40, 90, 80, 15, 15, 95, 30, 10, 30),
        (40, 60, 80, 50, 70, 75, 80),
        0.8,
    ),
    Archetype(
        "The Long-Gamer",
        "Thinks in decades, not seasons.",
        "Long-Gamers want a deep farm and a team built to last.",
        (30, 50, 30, 20, 30, 95, 80, 20, 40, 60, 10),
        (90, 50, 10, 20, 20, 25, 45),
        -0.6,
    ),
    Archetype(
        "The Corporate Board",
        "Wants steady returns and no headlines.",
        "Corporate Boards want steady profits and no drama.",
        (50, 30, 80, 50, 40, 40, 30, 20, 30, 85, 10),
        (55, 45, 50, 30, 20, 30, 35),
        0.4,
    ),
    Archetype(
        "The Grudge Holder",
        "Lose to anyone you like, except them.",
        "Grudge Holders want to beat one team above all others.",
        (60, 40, 30, 30, 50, 30, 30, 30, 40, 40, 95),
        (45, 55, 70, 50, 80, 70, 70),
    ),
    Archetype(
        "The People's Owner",
        "Fans first, last and always.",
        "People's Owners want the fans happy and the park full.",
        (50, 40, 15, 85, 95, 30, 50, 50, 70, 40, 50),
        (60, 50, 50, 30, 40, 55, 55),
    ),
    Archetype(
        "The Absentee",
        "Rarely calls. When they do, it's bad news.",
        "Absentee owners mostly leave the GM alone, as long as the money's right.",
        (40, 30, 50, 30, 30, 30, 20, 20, 20, 50, 20),
        (85, 40, 50, 5, 20, 5, 40),
    ),
    Archetype(
        "The Meddler",
        "Has an opinion on every move.",
        "Meddlers want a say in everything, and a winner.",
        (60, 50, 50, 50, 50, 50, 50, 50, 50, 30, 40),
        (25, 60, 70, 95, 80, 95, 60),
    ),
)
ARCHETYPES_BY_NAME = {a.name: a for a in ARCHETYPES}
PER_ARCHETYPE = 8
JITTER = 8
SEED = 2027


def wants(archetype: str) -> str:
    """What owners of this archetype want, in words, or "" if it isn't one
    of the starting archetypes."""
    arch = ARCHETYPES_BY_NAME.get(archetype)
    return arch.wants if arch else ""


def seed(rng: random.Random | None = None) -> list[dict]:
    """The starting library: PER_ARCHETYPE owners from each archetype, each
    with jittered weights and traits and a random name, all at
    DEFAULT_CHANCE."""
    rng = rng or random.Random(SEED)
    names = NameGenerator(rng=rng)
    used: set[str] = set()
    out = []

    def jitter(v: int) -> int:
        return max(0, min(100, v + rng.randint(-JITTER, JITTER)))

    for arch in ARCHETYPES:
        for _ in range(PER_ARCHETYPE):
            name = ""
            while not name or name in used:
                first, last = names.full("either")
                name = f"{first.title()} {last.title()}"
            used.add(name)
            out.append(
                {
                    "name": name,
                    "bio": arch.bio,
                    "archetype": arch.name,
                    "weights": {k: jitter(v) for k, v in zip(WEIGHTS, arch.weights)},
                    "traits": {k: jitter(v) for k, v in zip(TRAIT_KEYS, arch.traits)},
                    "chance": DEFAULT_CHANCE,
                }
            )
    return out


# ── The draw ─────────────────────────────────────────────────────────────────
# How much the market moves the odds: a market-5 team draws a Tycoon
# (tilt 1) 1 + MARKET_PULL times as often as an average team would.
MARKET_PULL = 0.5
MIN_MARKET, MID_MARKET, MAX_MARKET = 1, 3, 5


def market_factor(archetype: str, market: int) -> float:
    """How much more (or less) likely a team of this market size is to
    draw an owner of this archetype: 1 for an average market."""
    arch = ARCHETYPES_BY_NAME.get(archetype)
    if not arch:
        return 1.0
    lean = (market - MID_MARKET) / (MAX_MARKET - MID_MARKET)  # -1 to 1
    return max(0.1, 1 + MARKET_PULL * arch.market_tilt * lean)


def choose(
    pool: list[dict], taken: set[str], market: int, rng: random.Random
) -> dict | None:
    """An owner from pool ({id, archetype, chance, ...}) for a team of this
    market size, weighted by chance and the market tilt, leaving out those
    in taken. Chance 0 is never picked. When every pickable owner is taken,
    repeats are allowed. None if nothing is pickable."""
    pickable = [o for o in pool if o["chance"] > 0]
    fresh = [o for o in pickable if o["id"] not in taken] or pickable
    if not fresh:
        return None
    weights = [o["chance"] * market_factor(o["archetype"], market) for o in fresh]
    return rng.choices(fresh, weights=weights)[0]


def choose_rival(
    team_id: str, division_mates: list[str], others: list[str], rng: random.Random
) -> str | None:
    """The team an owner most wants to beat: usually a division rival, now
    and then anyone in the league."""
    mates = [t for t in division_mates if t != team_id]
    rest = [t for t in others if t != team_id]
    if mates and (not rest or rng.random() < 0.8):
        return rng.choice(mates)
    return rng.choice(rest) if rest else None
