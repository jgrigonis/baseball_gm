# src/league/finances.py
"""
Fan interest, revenue and owner-set budgets (plans/owners.md, D1 to D3).

A light money model, just enough for owners to set budgets and judge profit:

- **Fan interest** per team, 0 to 100, starts at FAN_START, moved by the
  league's backstory seasons as if they were real ones. At each season's
  end it moves part of the way toward a target set by the record, the
  playoffs, a title and the team's All-Stars.
- **Revenue** per season: a league-wide base, times the team's market size
  (the team pool's 1 to 5), times how interested its fans are, plus a gate
  for every home playoff game and popularity money when fans are keen.
- **Budget**: what the owner will spend on payroll and the front office
  (src/league/budget.py DEPARTMENTS). The league sets one payroll cap for every team
  (src/league/budget.py: the average payroll, then last season's average
  payroll plus 5% each season after), and
  each owner gives the GM a leash from it by their Spending trait: a miser
  wants payroll under the cap, a spender lets it go well over.
- The revenue base is scaled so an owner who spends an average share of
  revenue (from about 45% for a miser to 75% for a spender) would spend
  about the cap.
- **Profit** = revenue plus any share of the league's luxury tax (teams
  under the cap split it), minus payroll, luxury tax, fixed costs, the
  front office and the minor leagues (src/league/budget.py
  minor_league_cost). Nothing
  carries over between seasons; owners only read it.

Speed Blitz has no budgets, so none of this runs there.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.league import budget as bg

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
# The playoff, title and All-Star bonuses add about this much to an average
# team's target; it comes back off, so fan interest doesn't creep up across a
# league.
FAN_DRIFT = 7

# Revenue multiplier by market size, and what the Budget tab calls it.
MARKET_MULT = {1: 0.80, 2: 0.90, 3: 1.00, 4: 1.12, 5: 1.25}
MARKET_NAMES = {1: "Small", 2: "Modest", 3: "Mid-size", 4: "Big", 5: "Huge"}
# Fan interest 0 is FAN_MULT_LOW x revenue, 100 is FAN_MULT_LOW + FAN_MULT_SPAN.
FAN_MULT_LOW = 0.80
FAN_MULT_SPAN = 0.40
# Share of revenue an owner spends on payroll: Spending 0 to 100.
SHARE_LOW = 0.45
SHARE_SPAN = 0.30
# Each home playoff game earns this share of the league's average revenue
# (Josh, 2026-11-07: tripled from 1.2%, so October pays).
PLAYOFF_GATE = 0.036
# Popularity money (Josh, 2026-11-07): fan interest above POPULARITY_FROM
# earns extra revenue, rising evenly to POPULARITY_SHARE of the league's
# average revenue at 100, so a popular team can carry a tax bill. It goes by
# fan interest coming into the season. Under POPULARITY_FROM earns nothing.
POPULARITY_FROM = 55
POPULARITY_SHARE = 0.15
# Fixed costs (staff, the ballpark, travel): this share of the league's
# average revenue, the same for every team (Josh, 2026-11-07: up from 20%
# to trim the average team's profit from about +$50M to about +$25M).
FIXED_COSTS = 0.26

ROUNDING = 100_000

# Ticket prices (Josh, 2026-11-07): the GM sets them on a 1 to 10 slider
# between seasons. Higher prices take more at the gate this season, with
# less and less extra at the top, but push the fans' target down, so fan
# interest (and the revenue that follows it) slips over the seasons; low
# prices cost money now and win fans back. 5 is where every team starts.
TICKET_LEVELS = tuple(range(1, 11))
TICKET_DEFAULT = 5
TICKET_NAMES = (
    "Giveaway", "Bargain", "Cheap", "Value", "Standard",
    "Pricey", "Steep", "Premium", "Luxury", "Gouging",
)  # fmt: skip
# Regular season revenue multiplier by level.
TICKET_REVENUE = (0.85, 0.90, 0.94, 0.97, 1.00, 1.03, 1.05, 1.06, 1.065, 1.07)
# Points added to the fans' end-of-season target by level.
TICKET_FANS = (8, 6, 4, 2, 0, -2, -4, -7, -10, -14)


def _round(value: float) -> int:
    return round(value / ROUNDING) * ROUNDING


def market_mult(market: int) -> float:
    return MARKET_MULT.get(int(market), 1.0)


def fan_mult(fans: float) -> float:
    return FAN_MULT_LOW + FAN_MULT_SPAN * max(0.0, min(100.0, fans)) / 100


def spend_share(spending: int) -> float:
    """The share of revenue an owner with this Spending trait pays out."""
    return SHARE_LOW + SHARE_SPAN * max(0, min(100, spending)) / 100


def ticket_level(level) -> int:
    """A ticket price level, 1 to 10 (the default when unset)."""
    if level is None:
        return TICKET_DEFAULT
    return max(TICKET_LEVELS[0], min(TICKET_LEVELS[-1], int(level)))


def ticket_mult(level) -> float:
    return TICKET_REVENUE[ticket_level(level) - 1]


def ticket_fans(level) -> int:
    return TICKET_FANS[ticket_level(level) - 1]


def ticket_name(level) -> str:
    return TICKET_NAMES[ticket_level(level) - 1]


def ticket_revenue(revenue: int, level) -> int:
    """Regular season revenue at these ticket prices."""
    return _round(revenue * ticket_mult(level))


def fan_target(
    win_pct: float,
    made_playoffs: bool,
    champion: bool,
    all_stars: int,
    tickets: int = 0,
) -> float:
    target = 50 + (win_pct - 0.5) * FAN_PER_WIN_PCT + tickets
    target += FAN_PLAYOFFS if made_playoffs else 0
    target += FAN_TITLE if champion else 0
    target += FAN_PER_ALL_STAR * min(all_stars, FAN_MAX_ALL_STARS)
    return target - FAN_DRIFT


def fans_after(
    fans: float,
    win_pct: float,
    made_playoffs: bool,
    champion: bool,
    all_stars: int,
    ticket_price=None,
    marketing=None,
) -> int:
    """Fan interest after a season, with this season's ticket prices and
    marketing department level (None: the defaults)."""
    nudge = ticket_fans(ticket_price) + (
        0 if marketing is None else bg.marketing_fans(marketing)
    )
    target = fan_target(win_pct, made_playoffs, champion, all_stars, nudge)
    after = fans + FAN_STEP * (target - fans)
    return int(round(max(FAN_MIN, min(FAN_MAX, after))))


@dataclass(frozen=True)
class TeamMoney:
    market: int
    fans: float
    spending: int
    # How far the owner's bank is up (or down) since it started.
    bank_change: int = 0


@dataclass(frozen=True)
class Plan:
    """A team's money plan for a season: what it should take in before the
    playoffs, and the budget its owner gives the GM."""

    revenue: int
    budget: int


def plan(cap: int, teams: dict[str, TeamMoney]) -> dict[str, Plan]:
    """Each team's revenue and budget for a season under the league's cap."""
    if not teams:
        return {}
    pull = {t: market_mult(m.market) * fan_mult(m.fans) for t, m in teams.items()}
    raw = {t: pull[t] * spend_share(m.spending) for t, m in teams.items()}
    mean = sum(raw.values()) / len(raw)
    base = cap / mean  # league revenue at market 3, fans 50
    return {
        t: Plan(
            revenue=_round(base * pull[t]),
            budget=bg.owner_budget(cap, m.spending, m.bank_change)
            + bg.standard_front_office(cap),
        )
        for t, m in teams.items()
    }


def popularity_money(average_revenue: float, fans: float) -> int:
    """What a team's popularity earns in a season."""
    over = max(0.0, min(100.0, fans) - POPULARITY_FROM) / (100 - POPULARITY_FROM)
    return _round(average_revenue * POPULARITY_SHARE * over)


def playoff_gate(average_revenue: int, home_games: int) -> int:
    return _round(average_revenue * PLAYOFF_GATE * home_games)


def fixed_costs(average_revenue: int) -> int:
    return _round(average_revenue * FIXED_COSTS)


def profit(
    revenue: int,
    payroll: int,
    luxury_tax: int,
    costs: int,
    tax_share: int = 0,
    front_office: int = 0,
    minor_league: int = 0,
) -> int:
    return (
        revenue + tax_share - payroll - luxury_tax - costs - front_office - minor_league
    )


def books(
    *,
    revenue: int,
    market: int,
    fans: float,
    playoff_gate: int,
    home_playoff_games: int,
    gate_per_game: int,
    tax_share: int,
    payroll: int,
    front_office: int,
    luxury_tax: int,
    costs: int,
    minor_league: int = 0,
    farm_help: int = 0,
    ticket_price=None,
    popularity: int = 0,
    profit: int | None = None,
) -> dict:
    """A team's season as money in and money out, for the Budget tab.

    Revenue is the league's base times the market and fan interest, so the
    base is backed out of it. The league covers an average farm's salaries
    (farm_help: it comes off everyone's fixed costs in assess) and each team
    pays its own minor leaguers. Ticket prices move the regular season
    revenue up or down (tickets). With a profit (a finished season) anything it
    doesn't explain shows as other costs; without one the profit is
    projected from the lines.
    """
    mm, fm = market_mult(market), fan_mult(fans)
    level = ticket_level(ticket_price)
    tickets = ticket_revenue(revenue, level) - revenue
    total_in = revenue + tickets + playoff_gate + popularity + tax_share + farm_help
    known_out = payroll + front_office + minor_league + luxury_tax + costs
    projected = profit is None
    if projected:
        profit = total_in - known_out
    other = total_in - known_out - profit
    return {
        "base": _round(revenue / (mm * fm)),
        "market": market,
        "market_name": MARKET_NAMES.get(int(market), "Mid-size"),
        "market_mult": mm,
        "fans": int(round(fans)),
        "fan_mult": fm,
        "revenue": revenue,
        "ticket_price": level,
        "ticket_name": ticket_name(level),
        "ticket_pct": round((ticket_mult(level) - 1) * 100, 1),
        "tickets": tickets,
        "playoff_gate": playoff_gate,
        "popularity": popularity,
        "popularity_from": POPULARITY_FROM,
        "home_playoff_games": home_playoff_games,
        "gate_per_game": gate_per_game,
        "tax_share": tax_share,
        "farm_help": farm_help,
        "total_in": total_in,
        "payroll": payroll,
        "front_office": front_office,
        "minor_league": minor_league,
        "luxury_tax": luxury_tax,
        "costs": costs,
        "other": other,
        "total_out": known_out + other,
        "profit": profit,
        "projected": projected,
    }
