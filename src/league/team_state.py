# src/league/team_state.py
"""
Team state: where a front office sees its team, and so how it acts
(plans/ai-gm-strategy.md, section 7). It replaces the old three-way trade
stance worked out from the standings alone.

    all-in       top tier now, window closing (old core or a weak future)
    contending   top tier now, healthy future
    retooling    good, not great, with a solid veteran core
    ramping-up   young core improving: the future looks better than now
    rebuilding   weak now and in the near future
    aging-out    middling now, falling future, old roster

This module is the pure part: the inputs a state is worked out from, the
classification, and stickiness. src/api/services/team_states.py gathers the
inputs and stores the result in team_states.

Strength is ai_evaluator.team_strength, now and in a couple of years (ratings
moved by the age curve), ranked in the league. Ranks are shares from 0 (best)
to 1 (worst), so they mean the same in a 6-team league and a 30-team one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

STATES = (
    "all-in",
    "contending",
    "retooling",
    "ramping-up",
    "rebuilding",
    "aging-out",
)

LABELS = {
    "all-in": "All-in",
    "contending": "Contending",
    "retooling": "Retooling",
    "ramping-up": "Ramping up",
    "rebuilding": "Rebuilding",
    "aging-out": "Aging out",
}

# What a state means for trades: buyers look for help now, sellers move
# veterans for younger players. The rest trade less.
BUYERS = {"all-in", "contending"}
SELLERS = {"rebuilding", "aging-out"}

# Tiers of a rank share: the top third and the bottom third.
TOP = 1 / 3
BOTTOM = 2 / 3
# Standings, once STANDINGS_MIN_GAMES are played, decide how good a team is
# now: in a playoff spot or within CONTENDER_GB of one is top tier, more than
# SELLER_GB back is bottom tier.
STANDINGS_MIN_GAMES = 20
CONTENDER_GB = 5
SELLER_GB = 10
# An old core: the best players' average age OLDER_BY years past the
# league's, or OLD_SHARE of their value from players past OLD_AGE. A young
# core is YOUNGER_BY years under the league's.
OLDER_BY = 1.0
YOUNGER_BY = 1.0
OLD_AGE = 32
OLD_SHARE = 0.25
# How far the future rank has to move from today's to count as rising or
# falling.
RISING = 0.15
FALLING = 0.25

# Stickiness. A state holds for at least MIN_CHECKPOINTS checkpoints, and a
# change takes the same answer at two checkpoints in a row, unless the team
# jumps from one end of the league to the other.
MIN_CHECKPOINTS = 3


@dataclass(frozen=True)
class Inputs:
    """What a state is worked out from."""

    teams: int
    rank_now: float  # 0 best, 1 worst, by strength now
    rank_future: float  # the same, in a couple of years
    core_age: float  # average age of the 15 most valuable players
    league_core_age: float  # the same, averaged over the league
    old_share: float  # share of their value from players past OLD_AGE
    farm_rank: float  # 0 best: young players not on the 26-man, by future value
    played: int = 0  # games this season
    games_back: float | None = None  # from the last playoff spot; None out of season

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def standings_count(self) -> bool:
        return self.games_back is not None and self.played >= STANDINGS_MIN_GAMES

    @property
    def tier_now(self) -> str:
        """top, middle or bottom, today."""
        if self.standings_count:
            if self.games_back <= CONTENDER_GB:
                return "top"
            if self.games_back > SELLER_GB:
                return "bottom"
            return "middle"
        return _tier(self.rank_now)

    @property
    def old(self) -> bool:
        return (
            self.core_age >= self.league_core_age + OLDER_BY
            or self.old_share >= OLD_SHARE
        )

    @property
    def young(self) -> bool:
        return self.core_age <= self.league_core_age - YOUNGER_BY

    @property
    def rising(self) -> bool:
        return self.rank_future <= self.rank_now - RISING

    @property
    def falling(self) -> bool:
        return self.rank_future >= self.rank_now + FALLING


def _tier(rank: float) -> str:
    if rank < TOP:
        return "top"
    if rank >= BOTTOM:
        return "bottom"
    return "middle"


def classify(i: Inputs) -> str:
    """The state these inputs call for, before stickiness."""
    tier = i.tier_now
    future = _tier(i.rank_future)
    if tier == "top":
        # The window's closing: an old core, or not much behind it.
        if i.old or i.falling or future == "bottom":
            return "all-in"
        return "contending"
    if tier == "middle":
        if i.rising or (i.young and future == "top"):
            return "ramping-up"
        if i.old and (i.falling or future == "bottom"):
            return "aging-out"
        return "retooling"
    # Bottom tier: a young team with a good future and farm is on its way up.
    if future == "top" or (i.young and i.rising and i.farm_rank < BOTTOM):
        return "ramping-up"
    return "rebuilding"


@dataclass(frozen=True)
class Previous:
    """The team's stored state this season, as stickiness needs it."""

    state: str
    held: int  # checkpoints it's held for, counting the one it was set at
    candidate: str  # what classify() said at the last checkpoint
    tier: str  # tier_now at the last checkpoint


def settle(previous: Previous | None, inputs: Inputs) -> tuple[str, int]:
    """The state to store at this checkpoint, and how many checkpoints it's
    held for. Moving out of a state takes the same answer twice in a row,
    after it's held for MIN_CHECKPOINTS, unless the team went from one end of
    the league to the other."""
    candidate = classify(inputs)
    if previous is None or previous.state not in STATES:
        return candidate, 1
    if candidate == previous.state:
        return previous.state, previous.held + 1
    big_swing = {previous.tier, inputs.tier_now} == {"top", "bottom"}
    settled = previous.held >= MIN_CHECKPOINTS and previous.candidate == candidate
    if big_swing or settled:
        return candidate, 1
    return previous.state, previous.held + 1


def describe(state: str) -> str:
    """How the front office sees it, for the standings page."""
    return {
        "all-in": "an all-in team: the window is now",
        "contending": "a contender",
        "retooling": "a team that's retooling",
        "ramping-up": "a team that's ramping up",
        "rebuilding": "a team that's rebuilding",
        "aging-out": "a team that's aging out",
    }.get(state, "")
