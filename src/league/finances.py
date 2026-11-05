# src/league/finances.py
"""
Fan interest, revenue and owner-set budgets (plans/owners.md, D1 to D3).

A light money model, just enough for owners to set budgets and judge profit:

- **Fan interest** per team, 0 to 100, starts at FAN_START. At each season's
  end it moves part of the way toward a target set by the record, the
  playoffs, a title and the team's All-Stars.
- **Revenue** per season: a league-wide base, times the team's market size
  (the team pool's 1 to 5), times how interested its fans are, plus a gate
  for every home playoff game.
- **Budget**: the owner gives the GM a share of revenue to spend on payroll,
  from about 45% (a miser) to 75% (spends to win), by their Spending trait.
  The base is scaled so the league's average budget is what the flat budget
  would have been (src/league/budget.py: the average payroll, then 5% more a
  season), so payrolls already in place still fit.
- **Profit** = revenue minus payroll, luxury tax and fixed costs. Nothing
  carries over between seasons; owners only read it.

Speed Blitz has no budgets, so none of this runs there.
"""

from __future__ import annotations

from dataclasses import dataclass

FAN_START = 50
FAN_MIN, FAN_MAX = 5, 95
# How far fan interest moves toward its target each season.
FAN_STEP = 0.35
# Target: 50 at .500, 25 points for every 100 points of win %.
FAN_PER_WIN_PCT = 250
FAN_PLAYOFFS = 10
FAN_TITLE = 10
FAN_PER_ALL_STAR = 2
FAN_MAX_ALL_STARS = 4

# Revenue multiplier by market size.
MARKET_MULT = {1: 0.80, 2: 0.90, 3: 1.00, 4: 1.12, 5: 1.25}
# Fan interest 0 is FAN_MULT_LOW x revenue, 100 is FAN_MULT_LOW + FAN_MULT_SPAN.
FAN_MULT_LOW = 0.80
FAN_MULT_SPAN = 0.40
# Share of revenue an owner spends on payroll: Spending 0 to 100.
SHARE_LOW = 0.45
SHARE_SPAN = 0.30
# Each home playoff game earns this share of the league's average revenue.
PLAYOFF_GATE = 0.012
# Fixed costs (staff, the ballpark, travel): this share of the league's
# average revenue, the same for every team.
FIXED_COSTS = 0.20

ROUNDING = 100_000


def _round(value: float) -> int:
    return round(value / ROUNDING) * ROUNDING


def market_mult(market: int) -> float:
    return MARKET_MULT.get(int(market), 1.0)


def fan_mult(fans: float) -> float:
    return FAN_MULT_LOW + FAN_MULT_SPAN * max(0.0, min(100.0, fans)) / 100


def spend_share(spending: int) -> float:
    """The share of revenue an owner with this Spending trait pays out."""
    return SHARE_LOW + SHARE_SPAN * max(0, min(100, spending)) / 100


def fan_target(
    win_pct: float, made_playoffs: bool, champion: bool, all_stars: int
) -> float:
    target = 50 + (win_pct - 0.5) * FAN_PER_WIN_PCT
    target += FAN_PLAYOFFS if made_playoffs else 0
    target += FAN_TITLE if champion else 0
    target += FAN_PER_ALL_STAR * min(all_stars, FAN_MAX_ALL_STARS)
    return target


def fans_after(
    fans: float, win_pct: float, made_playoffs: bool, champion: bool, all_stars: int
) -> int:
    """Fan interest after a season."""
    target = fan_target(win_pct, made_playoffs, champion, all_stars)
    after = fans + FAN_STEP * (target - fans)
    return int(round(max(FAN_MIN, min(FAN_MAX, after))))


@dataclass(frozen=True)
class TeamMoney:
    market: int
    fans: float
    spending: int


@dataclass(frozen=True)
class Plan:
    """A team's money plan for a season: what it should take in before the
    playoffs, and the budget its owner gives the GM."""

    revenue: int
    budget: int


def plan(average_budget: int, teams: dict[str, TeamMoney]) -> dict[str, Plan]:
    """Each team's revenue and budget for a season, scaled so the league's
    average budget is average_budget."""
    if not teams:
        return {}
    pull = {t: market_mult(m.market) * fan_mult(m.fans) for t, m in teams.items()}
    raw = {t: pull[t] * spend_share(m.spending) for t, m in teams.items()}
    mean = sum(raw.values()) / len(raw)
    base = average_budget / mean  # league revenue at market 3, fans 50
    return {
        t: Plan(revenue=_round(base * pull[t]), budget=_round(base * raw[t]))
        for t in teams
    }


def playoff_gate(average_revenue: int, home_games: int) -> int:
    return _round(average_revenue * PLAYOFF_GATE * home_games)


def fixed_costs(average_revenue: int) -> int:
    return _round(average_revenue * FIXED_COSTS)


def profit(revenue: int, payroll: int, luxury_tax: int, costs: int) -> int:
    return revenue - payroll - luxury_tax - costs
