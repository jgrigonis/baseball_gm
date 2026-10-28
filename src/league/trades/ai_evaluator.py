# src/league/trades/ai_evaluator.py
#
# How an AI GM judges a trade offer. It doesn't add up player values: it
# compares its own team before and after the deal, so a fourth catcher adds
# almost nothing and three average players don't buy a star.
#
#   value(player) = (rating - REPLACEMENT) ** CONVEXITY, 0 below replacement
#
# Team strength weights each player by how much he'd play: the best 9 hitters
# and 5 starters count in full, the bench and bullpen less, the rest barely.
# The AI scores the deal twice, for this season (injured players count for the
# share of the season they'll be back for) and for the future (ratings moved by
# the age curve), and blends the two by its stance: a contender cares about
# now, a seller about later. A draft pick counts as the prospect it's expected
# to bring, for the future only.
#
# It accepts if the gain beats a margin of what it gives up. The margin moves a
# little, seeded by the two teams and the league date, so sending the same
# offer again the same day gets the same answer. Only visible ratings are
# used, never hidden talent caps, so its answers don't give those away.

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from functools import cached_property

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.player.player_value import RELIEVER_DISCOUNT

# Tuning (see plans/trades.md). Ratings run 0-100: on a 40-man the median is
# about 58 and the best are in the 70s; organization players are about 50.
REPLACEMENT = 50
CONVEXITY = 1.7

HITTER_DEPTH = [1.0] * 9 + [0.35] * 4 + [0.1] * 4
STARTER_DEPTH = [1.0] * 5
RELIEVER_DEPTH = [0.5] * 8 + [0.1] * 3

# Blend of (now, future) by stance.
STANCE_WEIGHTS = {
    "contender": (0.8, 0.2),
    "neutral": (0.5, 0.5),
    "seller": (0.2, 0.8),
}

BASE_MARGIN = 0.08
MARGIN_NOISE = 0.04


def age_shift(age: int) -> int:
    """Rating change to expect over the next couple of seasons at this age."""
    if age <= 22:
        return 3
    if age <= 25:
        return 2
    if age <= 28:
        return 0
    if age <= 31:
        return -2
    if age <= 34:
        return -5
    return -9


def value(rating: float) -> float:
    return max(0.0, rating - REPLACEMENT) ** CONVEXITY


@dataclass(frozen=True)
class Asset:
    """One player as the AI sees him."""

    id: str
    name: str
    is_pitcher: bool
    hit: int  # overall rating as a hitter
    sp: int
    rp: int  # already discounted to starter terms
    age: int
    injured_days: int = 0
    # A draft pick (src/league/trades/draft_picks.py): a prospect who counts
    # for the future but doesn't play this season.
    future_only: bool = False

    @classmethod
    def from_record(cls, p: PlayerRecord, injured_days: int = 0) -> Asset:
        r = PlayerEvaluator.rate_player(p.skills, p.throws)
        return cls(
            id=p.id,
            name=p.name,
            is_pitcher=p.is_pitcher(),
            hit=r["overall_player"],
            sp=r["sp"],
            rp=round(r["rp"] * RELIEVER_DISCOUNT),
            age=p.age,
            injured_days=injured_days,
        )

    @property
    def rating(self) -> int:
        return max(self.sp, self.rp) if self.is_pitcher else self.hit

    @cached_property
    def values(self) -> dict[str, tuple[float, float]]:
        """(now, future) value of each rating, worked out once: the AI's
        trade search weighs the same players many times."""
        shift = age_shift(self.age)
        return {
            k: (value(r), value(r + shift))
            for k, r in (("hit", self.hit), ("sp", self.sp), ("rp", self.rp))
        }


def team_strength(
    assets: list[Asset], future: bool = False, days_left: int = 1
) -> float:
    """How good a team is with these players, weighting each by how much he'd
    play. For now: injured players count for the share of the remaining
    season they're back for. For the future: ratings shift with age."""

    def adj(a: Asset, kind: str) -> float:
        now, later = a.values[kind]
        if future:
            return later
        if a.future_only:
            return 0.0
        if not a.injured_days:
            return now
        return now * (1 - min(1.0, a.injured_days / max(1, days_left)))

    hitters = sorted((adj(a, "hit") for a in assets if not a.is_pitcher), reverse=True)
    pitchers = [(adj(a, "sp"), a) for a in assets if a.is_pitcher]
    pitchers.sort(key=lambda x: x[0], reverse=True)
    starters = [v for v, _ in pitchers[: len(STARTER_DEPTH)]]
    relief = sorted(
        (adj(a, "rp") for _, a in pitchers[len(STARTER_DEPTH) :]), reverse=True
    )
    total = sum(w * v for w, v in zip(HITTER_DEPTH, hitters))
    total += sum(w * v for w, v in zip(STARTER_DEPTH, starters))
    total += sum(w * v for w, v in zip(RELIEVER_DEPTH, relief))
    return total


def strengths(assets: list[Asset], days_left: int) -> tuple[float, float]:
    """A team's (now, future) strength."""
    return (
        team_strength(assets, days_left=days_left),
        team_strength(assets, future=True),
    )


@dataclass
class Verdict:
    accept: bool
    reason: str
    score: float = 0.0
    threshold: float = 0.0
    details: dict = field(default_factory=dict)


def margin(ai_team_id: str, other_team_id: str, on: str) -> float:
    """The share of what it gives up the AI wants to win by, fixed for a pair
    of teams on one league date."""
    seed = hashlib.sha256(f"{ai_team_id}|{other_team_id}|{on}".encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8], "big"))
    return BASE_MARGIN + rng.uniform(-MARGIN_NOISE, MARGIN_NOISE)


def evaluate(
    roster: list[Asset],
    giving: list[Asset],
    getting: list[Asset],
    stance: str,
    days_left: int,
    margin_share: float,
    base: tuple[float, float] | None = None,
) -> Verdict:
    """Judge a deal from the AI team's side. roster is its whole organization
    today; giving is what it would send, getting what it would receive. base
    is the roster's (now, future) strength, when the caller already has it."""
    w_now, w_future = STANCE_WEIGHTS[stance]
    give_ids = {a.id for a in giving}
    after = [a for a in roster if a.id not in give_ids] + list(getting)
    if base is None:
        base = strengths(roster, days_left)

    d_now = team_strength(after, days_left=days_left) - base[0]
    d_future = team_strength(after, future=True) - base[1]
    score = w_now * d_now + w_future * d_future

    # What it gives up, player by player, is what the margin is measured on.
    out = sum(
        w_now * team_strength([a], days_left=days_left)
        + w_future * team_strength([a], future=True)
        for a in giving
    )
    threshold = margin_share * out
    accept = score > 0 and score >= threshold
    details = {"d_now": d_now, "d_future": d_future, "out": out}
    if accept:
        return Verdict(True, "Deal.", score, threshold, details)
    return Verdict(
        False,
        _reason(giving, getting, stance, d_now, d_future, score, days_left),
        score,
        threshold,
        details,
    )


def _reason(giving, getting, stance, d_now, d_future, score, days_left) -> str:
    best = max(giving, key=lambda a: a.rating) if giving else None
    hurt = [a for a in getting if a.injured_days > days_left / 2]
    if hurt:
        return f"We can't take on {hurt[0].name} while he's hurt."
    if stance == "contender" and d_now < 0:
        return "We're in the race. This makes us worse this season."
    if stance == "seller" and d_future < 0:
        return "We're building for later. We'd want younger talent back."
    if len(getting) > len(giving) and d_now <= 0:
        return "That's a lot of players for not much. We'd rather have one good one."
    if score > 0 and best:
        return f"Close, but we'd want a little more for {best.name}."
    if best:
        return f"Not enough coming back for {best.name}."
    return "That doesn't work for us."
