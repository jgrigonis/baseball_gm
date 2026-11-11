# src/league/trades/ai_proposer.py
#
# How an AI GM looks for a trade to offer (plans/trades.md, section 7). It
# works with the same judgement it uses to answer offers (ai_evaluator): a
# deal has to make its own team better by its margin, and it has to look
# like a deal the other side would take, judged the same way from their side.
#
# The search is kept small so it can run between game days:
#   - targets: the other team's healthy players who'd help most, best first
#     (MAX_TARGETS of them)
#   - what it offers: its own healthy players that cost it least and are worth
#     most to the other side (MAX_GIVERS of them), one at a time and then in
#     pairs, cheapest first
# Of the deals that work for both sides, it keeps the one that helps it most.
# Team states drive the trades: a contender buys players who help now, a
# rebuilding team sells veterans for younger ones, because each judges by its
# own weights. Each side also sees every player through its own GM's
# stats-vs-scouting lens, and tilts now against later by its time horizon.

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations

from src.league.trades import ai_evaluator
from src.league.trades.ai_evaluator import Asset

MAX_TARGETS = 5
MAX_GIVERS = 8
MAX_GIVE = 2


@dataclass
class Side:
    """One team as the search sees it."""

    team_id: str
    state: str  # its team state (src/league/team_state.py)
    roster: list[Asset]  # everyone it owns
    tradeable: set[str]  # ids it can trade (organization, healthy)
    margin: float  # the share of what it gives up it wants to win by
    stats_weight: float = 0.0  # its GM's stats-vs-scouting, 0 to 1
    horizon: float = 0.0  # its GM's, -1 (builds for later) to 1 (wins now)
    # More payroll its owner will stand for (an AI team's); None: no limit.
    pay_room: int | None = None
    # Value points it charges per dollar a player is owed
    # (ai_evaluator.money_rate); 0: money doesn't count.
    money: float = 0.0
    _seen: dict[str, Asset] = field(default_factory=dict, repr=False)

    def see(self, assets: list[Asset]) -> list[Asset]:
        """Players as this side's GM sees them."""
        out = []
        for a in assets:
            seen = self._seen.get(a.id)
            if seen is None:
                seen = self._seen[a.id] = a.seen(self.stats_weight)
            out.append(seen)
        return out


@dataclass
class Deal:
    give: list[Asset]  # from the AI team
    get: list[Asset]  # from the other team
    score: float  # how much it helps the AI team


def _verdict(side: Side, giving, getting, days_left, margin, base):
    return ai_evaluator.evaluate(
        side.see(side.roster),
        side.see(giving),
        side.see(getting),
        side.state,
        days_left,
        margin,
        base,
        side.horizon,
        side.pay_room,
        side.money,
    )


def find_deal(
    me: Side, them: Side, days_left: int, avoid: set[frozenset[str]] = frozenset()
) -> Deal | None:
    """The best one-for-one or two-for-one deal for `me` that `them` would
    also take, or None. avoid: deals (each the set of player ids in it)
    already offered."""
    my_base = ai_evaluator.strengths(me.see(me.roster), days_left)
    their_base = ai_evaluator.strengths(them.see(them.roster), days_left)

    def gain(side, base, giving, getting):
        return _verdict(side, giving, getting, days_left, 0.0, base).score

    theirs = [a for a in them.roster if a.id in them.tradeable and not a.injured_days]
    targets = sorted(
        ((gain(me, my_base, [], [a]), a) for a in theirs),
        key=lambda x: x[0],
        reverse=True,
    )
    targets = [a for g, a in targets[:MAX_TARGETS] if g > 0]
    if not targets:
        return None

    mine = [a for a in me.roster if a.id in me.tradeable and not a.injured_days]
    surplus = []
    for a in mine:
        worth_to_them = gain(them, their_base, [], [a])
        if worth_to_them <= 0:
            continue
        cost_to_me = -gain(me, my_base, [a], [])
        surplus.append((cost_to_me - worth_to_them, cost_to_me, a))
    surplus.sort(key=lambda x: x[0])
    givers = [(cost, a) for _, cost, a in surplus[:MAX_GIVERS]]
    if not givers:
        return None

    packages = [[g] for g in givers]
    if MAX_GIVE >= 2:
        packages += [list(p) for p in combinations(givers, 2)]
    packages.sort(key=lambda p: sum(cost for cost, _ in p))

    best: Deal | None = None
    for target in targets:
        for package in packages:
            give = [a for _, a in package]
            if frozenset(a.id for a in give + [target]) in avoid:
                continue
            verdict = _verdict(me, give, [target], days_left, me.margin, my_base)
            if not verdict.accept:
                continue
            theirs_ok = _verdict(
                them, [target], give, days_left, them.margin, their_base
            )
            if not theirs_ok.accept:
                continue
            # The cheapest package that works for this target.
            if best is None or verdict.score > best.score:
                best = Deal(give, [target], verdict.score)
            break
    return best


# Shopping a player: every AI team's best offer for one of a GM's players.
# Each looks at the players it could send (the MAX_SHOP_GIVERS worth most to
# the shopping team), one at a time and in pairs, and keeps the package it
# would really take the deal for that helps the shopping team most.
MAX_SHOP_GIVERS = 10


@dataclass
class ShopOffer:
    give: list[Asset]  # from the AI team
    score: float  # how much it helps the shopping team, as it sees him
    # Not a deal it would take: the package it came closest to taking,
    # when it has none it would, to show the shopping GM. Only one it would
    # still come out ahead on, just not by its margin: one that leaves it
    # worse off isn't close to anything (NO_EVEN).
    short: bool = False


def shop_offer(
    ai: Side,
    seller: Side,
    target: Asset,
    days_left: int,
    blocked: set[str] = frozenset(),
) -> ShopOffer | None:
    """The AI team's best offer for `target`, the seller's player, or None
    if it has no deal it would take. blocked: its players who can't go to
    the seller (traded away by the seller this season). The seller judges
    as a person does, with no margin; the AI with its own."""
    offer = shop_offer_or_why(ai, seller, target, days_left, blocked)
    return offer if isinstance(offer, ShopOffer) and not offer.short else None


# Why an AI team made no shop offer, for the shopping GM: he doesn't help
# them, every deal it would take adds more salary than its owner allows, or
# it wants him but nothing it would part with is worth enough to the seller.
# Or he'd help on the field but his contract costs more than he's worth to
# them (ai_evaluator.money_cost). Or it wants him, but every player of its
# own the seller would want is worth more to it than he is: for a modest
# player, its best young prospects. That package isn't close to a deal, and
# shown as the one it "came closest with" it read as an absurd offer (Josh,
# 2026-11-11: an 18-year-old B- prospect for a D+).
NO_HELP, NO_ROOM, NO_MATCH, NO_VALUE = "fit", "pay", "price", "cost"
NO_EVEN = "over"


def shop_offer_or_why(
    ai: Side,
    seller: Side,
    target: Asset,
    days_left: int,
    blocked: set[str] = frozenset(),
) -> ShopOffer | str:
    """shop_offer, or why there's none (NO_HELP, NO_VALUE, NO_ROOM,
    NO_EVEN or NO_MATCH). When it wants him but no package passes its
    margin, the package it came closest to taking among those it would
    still come out ahead on, marked short and near; NO_EVEN when every
    package leaves it worse off; NO_MATCH when there's no package at all."""
    ai_base = ai_evaluator.strengths(ai.see(ai.roster), days_left)
    seller_base = ai_evaluator.strengths(seller.see(seller.roster), days_left)
    # Whether he'd help at all, before pay: the salary it sends back in a
    # package counts against his, so the budget is judged package by package.
    free = replace(ai, pay_room=None, _seen=ai._seen)
    if _verdict(free, [], [target], days_left, 0.0, ai_base).score <= 0:
        unpriced = replace(free, money=0.0, _seen=ai._seen)
        if _verdict(unpriced, [], [target], days_left, 0.0, ai_base).score > 0:
            return NO_VALUE
        return NO_HELP

    def for_seller(give):
        return _verdict(seller, [target], give, days_left, 0.0, seller_base).score

    mine = [
        a
        for a in ai.roster
        if a.id in ai.tradeable and not a.injured_days and a.id not in blocked
    ]
    worth = sorted(
        (
            (_verdict(seller, [], [a], days_left, 0.0, seller_base).score, a)
            for a in mine
        ),
        key=lambda x: x[0],
        reverse=True,
    )
    givers = [a for w, a in worth[:MAX_SHOP_GIVERS] if w > 0]
    packages = [[g] for g in givers]
    if MAX_GIVE >= 2:
        packages += [list(p) for p in combinations(givers, 2)]

    best: ShopOffer | None = None
    over_budget = False
    closest, closest_gap, worse_off = None, None, False
    for give in packages:
        v = _verdict(ai, give, [target], days_left, ai.margin, ai_base)
        if not v.accept:
            if v.reason == ai_evaluator.OVER_BUDGET_REASON:
                if not over_budget:
                    over_budget = _verdict(
                        free, give, [target], days_left, ai.margin, ai_base
                    ).accept
            elif v.score > 0:
                # Short of its margin.
                gap = v.score - v.threshold
                if closest_gap is None or gap > closest_gap:
                    closest, closest_gap = give, gap
            else:
                worse_off = True
            continue
        score = for_seller(give)
        if best is None or score > best.score:
            best = ShopOffer(give, score)
    if best is not None:
        return best
    if over_budget:
        return NO_ROOM
    if closest is not None:
        return ShopOffer(closest, for_seller(closest), short=True)
    if worse_off:
        return NO_EVEN
    return NO_MATCH


# Dumping salary: the shopping GM wants a player's salary off their books
# more than they want anything back. Each AI team with room says what it
# would take him for: it sends back one of its own cheapest, least-missed
# players (a trade needs a player or pick each way), and if he alone isn't
# worth it to them, the GM adds a sweetener of their own.
MAX_THROW_INS = 4
MAX_SWEETENERS = 8


@dataclass
class DumpOffer:
    give: list[Asset]  # the throw-in from the AI team
    add: list[Asset]  # the sweetener the seller adds (empty: none needed)
    saved: int  # payroll it takes off the seller's books this season
    cost: float  # what the sweetener is worth to the seller (0: none)


def dump_offer_or_why(
    ai: Side,
    seller: Side,
    target: Asset,
    days_left: int,
    blocked: set[str] = frozenset(),
) -> DumpOffer | str:
    """The cheapest way this AI team would take `target`'s salary: him
    alone for a throw-in if it can, otherwise with the least costly
    sweetener of the seller's that does it. Or why not: NO_ROOM when every
    deal it would take adds more salary than its owner allows, NO_MATCH
    when nothing the seller adds is enough."""
    ai_base = ai_evaluator.strengths(ai.see(ai.roster), days_left)
    seller_base = ai_evaluator.strengths(seller.see(seller.roster), days_left)
    free = replace(ai, pay_room=None, _seen=ai._seen)

    def cost_to_ai(a):
        return -_verdict(free, [a], [], days_left, 0.0, ai_base).score

    def cost_to_seller(a):
        return -_verdict(seller, [a], [], days_left, 0.0, seller_base).score

    theirs = [
        a
        for a in ai.roster
        if a.id in ai.tradeable and not a.injured_days and a.id not in blocked
    ]
    # The players it would miss least, the cheapest of those first.
    throw_ins = sorted(theirs, key=lambda a: (round(cost_to_ai(a), 1), a.salary))
    throw_ins = sorted(throw_ins[:MAX_THROW_INS], key=lambda a: a.salary)
    if not throw_ins:
        return NO_MATCH

    mine = [
        a
        for a in seller.roster
        if a.id in seller.tradeable and a.id != target.id and not a.injured_days
    ]
    sweeteners = sorted(((cost_to_seller(a), a) for a in mine), key=lambda x: x[0])[
        :MAX_SWEETENERS
    ]

    over_budget = False
    for cost, sweet in [(0.0, None)] + sweeteners:
        getting = [target] + ([sweet] if sweet else [])
        for throw in throw_ins:
            v = _verdict(ai, [throw], getting, days_left, ai.margin, ai_base)
            if v.accept:
                saved = sum(a.salary for a in getting) - throw.salary
                return DumpOffer(
                    [throw], [sweet] if sweet else [], saved, max(cost, 0.0)
                )
            if v.reason == ai_evaluator.OVER_BUDGET_REASON:
                over_budget = True
    return NO_ROOM if over_budget else NO_MATCH
