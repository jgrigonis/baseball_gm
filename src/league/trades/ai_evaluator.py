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
# the age curve), and blends the two by its team state
# (src/league/team_state.py): a contender cares about now, a rebuilding team
# about later. A draft pick counts as the prospect it's expected
# to bring, for the future only.
#
# It accepts if the gain beats a margin of what it gives up. The margin moves a
# little, seeded by the two teams and the league date, so sending the same
# offer again the same day gets the same answer. Only visible ratings and
# season stats are used, never hidden talent caps, so its answers don't give
# those away.
#
# The GM's persona (src/league/personas.py) leans on all of this: its time
# horizon tilts the now/future blend, its risk appetite scales the margin, and
# its stats-vs-scouting dial blends each player's ratings with how he's
# played (src/league/performance.py) before any of it is worked out.
#
# Contracts cost something too. Each player carries what he's owed above the
# minimum: the rest of this season, and a typical season of the next
# FUTURE_YEARS (his deal while it runs, then the arbitration share or market
# price he'd get). The AI charges a share of that against his worth, the
# money rate (money_rate): set by its money state (more when capped out or
# cutting costs, less when flush), less for a contender going for it. So an overpaid veteran can be worth less than
# nothing, and a cheap young star more than a fairly paid one.

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field, replace
from functools import cached_property

from src.league import money_state as ms
from src.league.team_state import BUYERS, SELLERS
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

# Blend of (now, future) by team state.
STATE_WEIGHTS = {
    "all-in": (0.95, 0.05),
    "contending": (0.8, 0.2),
    "retooling": (0.55, 0.45),
    "ramping-up": (0.35, 0.65),
    "rebuilding": (0.15, 0.85),
    "aging-out": (0.3, 0.7),
}

BASE_MARGIN = 0.08
MARGIN_NOISE = 0.04
# How far a win-now or a patient GM moves the now weight of its state.
HORIZON_TILT = 0.1


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
    # How his season stats compare to his ratings, in rating points, as a
    # hitter and as a pitcher (src/league/performance.py).
    form: tuple[float, float] = (0.0, 0.0)
    # He's asked his team for a trade (src/player/happiness.py), so it will
    # take less to move him.
    wants_out: bool = False
    # What he's owed this season on a guaranteed deal: what taking him on
    # adds to payroll.
    salary: int = 0
    # What he's owed above the league minimum (src/player/contracts.py):
    # this season, and a typical season of the next FUTURE_YEARS. Unlike
    # salary these count every deal, guaranteed or not; what the trade's
    # money is priced on.
    owed_now: int = 0
    owed_later: int = 0

    @classmethod
    def from_record(
        cls,
        p: PlayerRecord,
        injured_days: int = 0,
        form: tuple[float, float] = (0.0, 0.0),
        wants_out: bool = False,
        salary: int = 0,
        owed: tuple[int, int] = (0, 0),
    ) -> Asset:
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
            form=form,
            wants_out=wants_out,
            salary=salary,
            owed_now=owed[0],
            owed_later=owed[1],
        )

    def seen(self, stats_weight: float) -> Asset:
        """The player as a GM who gives his stats this weight sees him."""
        hit, pitch = self.form
        if not stats_weight or (not hit and not pitch):
            return self
        return replace(
            self,
            hit=round(self.hit + stats_weight * hit),
            sp=round(self.sp + stats_weight * pitch),
            rp=round(self.rp + stats_weight * pitch * RELIEVER_DISCOUNT),
            form=(0.0, 0.0),
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


def seen(assets: list[Asset], stats_weight: float) -> list[Asset]:
    """Players as a GM who gives stats this weight sees them."""
    if not stats_weight:
        return list(assets)
    return [a.seen(stats_weight) for a in assets]


def margin(ai_team_id: str, other_team_id: str, on: str, factor: float = 1.0) -> float:
    """The share of what it gives up the AI wants to win by, fixed for a pair
    of teams on one league date. factor is the persona's (cautious GMs want
    more)."""
    seed = hashlib.sha256(f"{ai_team_id}|{other_team_id}|{on}".encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8], "big"))
    return factor * (BASE_MARGIN + rng.uniform(-MARGIN_NOISE, MARGIN_NOISE))


def weights(state: str, horizon: float = 0.0) -> tuple[float, float]:
    """(now, future) weights for a team state, tilted by the GM's horizon
    (-1 builds for later, 1 wins now)."""
    if not horizon:
        return STATE_WEIGHTS[state]
    w_now = STATE_WEIGHTS[state][0] + HORIZON_TILT * horizon
    w_now = max(0.02, min(0.98, w_now))
    return w_now, 1 - w_now


# How much of a player who asked for a trade his AI team insists on getting
# back.
WANTS_OUT_SHARE = 0.5
# And how much less any team pays for one: everyone knows his team wants to
# move him (a share of his worth on his own).
WANTS_OUT_DISCOUNT = 0.2


OVER_BUDGET_REASON = "Our owner won't pay for that much more salary."
OVERPAID_REASON = "We can't take on {name}'s contract for what he'd give us."

# Pricing contracts. A season of value (value()) costs about this much on
# the market (src/player/contracts.py prime_salary over value() is close to
# $120K a point at every grade, above the minimum).
DOLLARS_PER_POINT = 120_000
# Seasons after this one a contract is priced over.
FUTURE_YEARS = 3
# Days in a regular season, to prorate what's left of this season's pay
# (src/api/services/trades.py OFFSEASON_DAYS_LEFT counts a whole one).
SEASON_DAYS = 180
# The share of a player's fair pay the AI counts against him comes from its
# money state (src/league/money_state.py: flush, balanced, capped out,
# cutting costs), and is tilted by its team state: a team going for it
# worries less about the bill.
STATE_MONEY = {
    "all-in": 0.8,
    "contending": 0.9,
    "retooling": 1.0,
    "ramping-up": 1.0,
    "rebuilding": 1.15,
    "aging-out": 1.1,
}


def money_share(money_state: str, state: str) -> float:
    """The share of fair pay an AI team charges against a player."""
    return ms.money_share(money_state) * STATE_MONEY.get(state, 1.0)


def money_rate(money_state: str | None, scale: float, state: str) -> float:
    """Value points an AI team charges per dollar owed: 0 when money
    doesn't matter to it (no budgets: money_state None). scale is how far
    salaries have grown with the cap (src/league/budget.py salary_scale)."""
    if money_state is None or scale <= 0:
        return 0.0
    return money_share(money_state, state) / (DOLLARS_PER_POINT * scale)


def money_cost(a: Asset, rate: float, days_left: int, w_now: float, w_future: float):
    """What a player's contract costs the AI, in value points, weighted
    like his play (now for the rest of this season, future a season)."""
    if not rate:
        return 0.0
    left = min(1.0, days_left / SEASON_DAYS)
    return rate * (w_now * left * a.owed_now + w_future * a.owed_later)


def evaluate(
    roster: list[Asset],
    giving: list[Asset],
    getting: list[Asset],
    state: str,
    days_left: int,
    margin_share: float,
    base: tuple[float, float] | None = None,
    horizon: float = 0.0,
    pay_room: int | None = None,
    money: float = 0.0,
) -> Verdict:
    """Judge a deal from the AI team's side. roster is its whole organization
    today; giving is what it would send, getting what it would receive, all
    as this GM sees them (seen()). base is the roster's (now, future)
    strength, when the caller already has it. horizon is the GM's, from -1
    (builds for later) to 1 (wins now). pay_room is how much more payroll
    its owner will stand for (None: no limit); a deal that adds more salary
    than that is off, however good. money is its money rate (money_rate):
    value points it charges per dollar owed."""
    added = sum(a.salary for a in getting) - sum(a.salary for a in giving)
    if pay_room is not None and added > 0 and added > pay_room:
        return Verdict(False, OVER_BUDGET_REASON, 0.0, 0.0, {"added": added})
    w_now, w_future = weights(state, horizon)
    give_ids = {a.id for a in giving}
    after = [a for a in roster if a.id not in give_ids] + list(getting)
    if base is None:
        base = strengths(roster, days_left)

    d_now = team_strength(after, days_left=days_left) - base[0]
    d_future = team_strength(after, future=True) - base[1]
    score = w_now * d_now + w_future * d_future

    def alone(a: Asset) -> float:
        return w_now * team_strength(
            [a], days_left=days_left
        ) + w_future * team_strength([a], future=True)

    # A player who asked out of his team is worth less to whoever takes him:
    # everyone knows his team wants to move him. The discount is a share of
    # what he'd add to this team, not of his worth on his own: a depth arm
    # who wouldn't crack its staff adds nothing, so nothing comes off.
    unhappy = {a.id for a in getting if a.wants_out}
    if unhappy:
        without = [a for a in after if a.id not in unhappy]
        adds = w_now * (
            team_strength(after, days_left=days_left)
            - team_strength(without, days_left=days_left)
        ) + w_future * (
            team_strength(after, future=True) - team_strength(without, future=True)
        )
        score -= WANTS_OUT_DISCOUNT * max(0.0, adds)

    # The money: what it takes on costs it, what it sends away saves it.
    def cost(a: Asset) -> float:
        return money_cost(a, money, days_left, w_now, w_future)

    d_money = sum(cost(a) for a in giving) - sum(cost(a) for a in getting)
    play = score
    score += d_money

    # What it gives up, player by player, is what the margin is measured on,
    # net of his contract. A player who asked out counts for less: his team
    # is ready to move him.
    out = sum(
        max(0.0, alone(a) * (WANTS_OUT_SHARE if a.wants_out else 1.0) - cost(a))
        for a in giving
    )
    threshold = margin_share * out
    accept = score > 0 and score >= threshold
    details = {"d_now": d_now, "d_future": d_future, "d_money": d_money, "out": out}
    if accept:
        return Verdict(True, "Deal.", score, threshold, details)
    if d_money < 0 and play > 0 and play >= threshold:
        # It would take the players; it's the money that stops it.
        priciest = max(getting, key=cost)
        return Verdict(
            False, OVERPAID_REASON.format(name=priciest.name), score, threshold, details
        )
    return Verdict(
        False,
        _reason(giving, getting, state, d_now, d_future, score, days_left),
        score,
        threshold,
        details,
    )


def _reason(giving, getting, state, d_now, d_future, score, days_left) -> str:
    best = max(giving, key=lambda a: a.rating) if giving else None
    hurt = [a for a in getting if a.injured_days > days_left / 2]
    if hurt:
        return f"We can't take on {hurt[0].name} while he's hurt."
    if state in BUYERS and d_now < 0:
        return "We're in the race. This makes us worse this season."
    if state in SELLERS and d_future < 0:
        # Worse for the future: either nothing coming back is young, or the
        # young players are, but not good enough to make up for what goes.
        young = [a for a in getting if age_shift(a.age) > 0]
        if not young:
            return "We're building for later. We'd want younger talent back."
        prospect = max(young, key=lambda a: a.rating)
        if best:
            return (
                f"We like young players, but {prospect.name} isn't enough "
                f"of a prospect to give up {best.name}."
            )
        return f"We like young players, but {prospect.name} isn't enough of a prospect."
    if len(getting) > len(giving) and d_now <= 0:
        return "That's a lot of players for not much. We'd rather have one good one."
    if score > 0 and best:
        return f"Close, but we'd want a little more for {best.name}."
    if best:
        return f"Not enough coming back for {best.name}."
    return "That doesn't work for us."
