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

from dataclasses import dataclass, field
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
