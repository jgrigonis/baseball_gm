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
  Three more lines on top: a broadcast deal, its price locked when it's
  signed, merchandise, what the team's good players sell, and a sponsor
  deal, steady or paid on how the team does this season. And the
  ballpark: upgrades the owner pays for from their bank (BALLPARK) earn
  money every season after they open.
- **Budget**: what the owner will spend on payroll and the front office
  (src/league/budget.py DEPARTMENTS). The league sets one payroll cap for every team
  (src/league/budget.py: the average payroll, then last season's average
  payroll plus 5% each season after), and
  each owner gives the GM a leash from it by their Spending trait: a miser
  wants payroll under the cap, a spender lets it go well over.
- The revenue base is scaled so an owner who spends an average share of
  revenue (from about 45% for a miser to 75% for a spender) would spend
  about the cap, then raised by REGULAR_SEASON_BOOST.
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
# Regular season revenue on top of the cap-matched base (Josh, 2026-11-09:
# regular season tickets brought in too little). Everything priced as a share
# of the league's average revenue (fixed costs, popularity, broadcast deals,
# the playoff gate) grows with it.
REGULAR_SEASON_BOOST = 1.25
# Each home playoff game earns this share of the league's average revenue
# (Josh, 2026-11-07: tripled from 1.2%, so October pays; 2026-11-09: five
# times that, 18% of the base before REGULAR_SEASON_BOOST).
PLAYOFF_GATE = 0.18 / REGULAR_SEASON_BOOST
# Popularity money (Josh, 2026-11-07): fan interest above POPULARITY_FROM
# earns extra revenue, rising evenly to POPULARITY_SHARE of the league's
# average revenue at 100, so a popular team can carry a tax bill. It goes by
# fan interest coming into the season. Under POPULARITY_FROM earns nothing.
POPULARITY_FROM = 55
POPULARITY_SHARE = 0.15
# Fixed costs (staff, the ballpark, travel): this share of the league's
# average revenue, the same for every team (Josh, 2026-11-07: up from 20%
# to trim the average team's profit to about +$25M a season; 26% still left
# about +$42M in a 6-season sim, so 32%).
FIXED_COSTS = 0.32

ROUNDING = 100_000

# Merchandise (Josh, 2026-11-09): every good player sells jerseys. What one
# sells in a season by his overall grade, at a MERCH_CAP payroll cap (it grows
# with the cap). An All-Star sells MERCH_ALL_STAR times as many, an MVP or Cy
# Young winner MERCH_AWARD times, and a player in his first year with a new
# team MERCH_NEW times, for the new team only (a new jersey). Each player's
# money goes to his teams by the share of his games he played for each.
MERCH_BY_GRADE = {"A+": 10_000_000, "A": 6_000_000, "A-": 3_000_000, "B+": 1_000_000}
MERCH_CAP = 160_000_000
MERCH_ALL_STAR = 1.5
MERCH_AWARD = 2.0
MERCH_NEW = 1.5
MERCH_AWARDS = ("mvp", "cy_young")
# Retro jerseys (Josh, 2026-11-09): every Hall of Famer sells HALL_JERSEY a
# season (at a MERCH_CAP cap) for the team he went in for, HALL_INDUCTION
# times that the season after he's elected. Times the same market, fans and
# marketing as the rest.
HALL_GRADE = "HOF"
HALL_JERSEY = 1_500_000
HALL_INDUCTION = 3.0
# The team's total is times its market (MARKET_MULT) and its fans: fan
# interest 0 is MERCH_FAN_LOW, 100 is MERCH_FAN_LOW + MERCH_FAN_SPAN.
MERCH_FAN_LOW = 0.6
MERCH_FAN_SPAN = 0.8
# And times the Marketing department, Bare bones to Elite.
MERCH_MARKETING = (0.8, 0.9, 1.0, 1.1, 1.2)

# Broadcast deals (Josh, 2026-11-09): a local TV deal, its price locked for
# its length when it's signed: a share of the league's average revenue,
# BROADCAST_FLOOR for the least attractive team up to BROADCAST_FLOOR +
# BROADCAST_SPAN for the most, times the market. Attractive = fan interest
# coming into the season and the win % of the last BROADCAST_SEASONS seasons,
# half each; win % runs from BROADCAST_WIN_LOW (nothing) to BROADCAST_WIN_LOW +
# BROADCAST_WIN_SPAN (all of it). A GM picks the length of a new deal;
# a long one pays a little more for locking the price in.
BROADCAST_FLOOR = 0.06
BROADCAST_SPAN = 0.10
BROADCAST_SEASONS = 3
BROADCAST_WIN_LOW = 0.35
BROADCAST_WIN_SPAN = 0.30
BROADCAST_YEARS = (2, 3, 5)
BROADCAST_DEFAULT_YEARS = 3
BROADCAST_LENGTH_MULT = {2: 1.0, 3: 1.0, 5: 1.05}

# Sponsors (Josh, 2026-11-09): the one money line that follows how the team
# does THIS season. Each season the GM takes one of two offers between
# seasons. Steady pays SPONSOR_SHARE of the league's average revenue times
# the market, whatever happens. Incentive pays SPONSOR_BASE of that up front,
# plus SPONSOR_PER_WIN_PCT times it for every point of win % over .500 (.600
# is +0.5), SPONSOR_PLAYOFFS for making the playoffs and SPONSOR_PER_ROUND for
# each playoff series won: a bad team gets less than Steady, a champion about
# twice it. A team that hasn't picked (every AI team) takes Incentive after a
# season over SPONSOR_AI_FROM, Steady otherwise.
SPONSOR_KINDS = ("steady", "incentive")
SPONSOR_NAMES = {"steady": "Steady", "incentive": "Incentive"}
SPONSOR_SHARE = 0.04
SPONSOR_BASE = 0.6
SPONSOR_PER_WIN_PCT = 5.0
SPONSOR_PLAYOFFS = 0.3
SPONSOR_PER_ROUND = 0.2
SPONSOR_AI_FROM = 0.540

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
TICKET_REVENUE = (0.80, 0.86, 0.91, 0.96, 1.00, 1.04, 1.07, 1.095, 1.115, 1.13)
# Points added to the fans' end-of-season target by level.
TICKET_FANS = (12, 9, 6, 3, 0, -3, -6, -10, -14, -19)


# Ballpark upgrades (Josh, 2026-11-09: stadium upgrades for rich owners).
# Each is built once, paid from the owner's bank (not the season's profit)
# and earns from the season it opens on. Costs are a share of the cap;
# money is a share of the league's average revenue times the market (and
# fan interest, for club seats), or a share of the team's own regular season
# revenue (a renovation). Paybacks run about 4 to 7 seasons, inside a
# 10-season league.
@dataclass(frozen=True)
class Project:
    key: str
    name: str
    what: str
    cost: float  # share of the cap
    earns: float = 0.0  # share of the league's average revenue, times the market
    by_fans: bool = False  # and times fan interest (fan_mult)
    revenue: float = 0.0  # share of the team's regular season revenue
    fans: int = 0  # points on the fans' end-of-season target, every season


BALLPARK = (
    Project(
        "club_seats", "Club seats",
        "Padded seats with their own bar, sold by the season. Keen fans pay more.",
        cost=0.375, earns=0.036, by_fans=True,
    ),
    Project(
        "suites", "Luxury suites",
        "Glassed-in boxes leased to companies. Big markets pay the most.",
        cost=0.75, earns=0.072,
    ),
    Project(
        "plaza", "Fan plaza and video board",
        "A plaza outside the gates and a giant screen. Fans warm to the team every season.",
        cost=0.25, fans=3,
    ),
    Project(
        "renovation", "Full renovation",
        "New concourses, food and seats all round. Every regular season ticket earns more.",
        cost=1.5, revenue=0.10,
    ),
)  # fmt: skip
BALLPARK_KEYS = tuple(p.key for p in BALLPARK)
# The owner only builds with savings to spare: their bank has to hold at
# least this many caps after paying.
BALLPARK_FLOOR = 1.0
# One project a season: it's built between seasons and opens on Opening Day.
BALLPARK_PER_SEASON = 1
# What the AI reckons a point of fan interest is worth a season, as a share
# of its regular season revenue (fan_mult: 0.4 of revenue over 100 points).
FAN_POINT_VALUE = FAN_MULT_SPAN / 100


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


def project(key) -> Project | None:
    return next((p for p in BALLPARK if p.key == key), None)


def project_cost(key, cap: int) -> int:
    p = project(key)
    return _round(cap * p.cost) if p else 0


def project_money(
    key,
    average_revenue: float,
    market: int,
    fans: float,
    revenue: int,
    ticket_price=None,
) -> int:
    """What one ballpark project earns in a season for this team: revenue
    is its regular season revenue before ticket prices."""
    p = project(key)
    if p is None:
        return 0
    value = average_revenue * p.earns * market_mult(market)
    if p.by_fans:
        value *= fan_mult(fans)
    value += ticket_revenue(revenue, ticket_price) * p.revenue
    return _round(value)


def ballpark_money(
    built,
    average_revenue: float,
    market: int,
    fans: float,
    revenue: int,
    ticket_price=None,
) -> int:
    """What the team's open ballpark projects earn this season."""
    return sum(
        project_money(k, average_revenue, market, fans, revenue, ticket_price)
        for k in set(built)
    )


def ballpark_fans(built) -> int:
    """Points the open ballpark projects add to the fans' target."""
    return sum(p.fans for p in BALLPARK if p.key in set(built))


def project_value(
    key,
    average_revenue: float,
    market: int,
    fans: float,
    revenue: int,
    ticket_price=None,
) -> float:
    """A season of the project as money, fan interest at FAN_POINT_VALUE a
    point (what AI owners weigh)."""
    p = project(key)
    if p is None:
        return 0.0
    return project_money(
        key, average_revenue, market, fans, revenue, ticket_price
    ) + p.fans * FAN_POINT_VALUE * ticket_revenue(revenue, ticket_price)


def payback(cost: int, per_season: float) -> float | None:
    """Seasons until a project pays for itself (None when it earns nothing)."""
    return cost / per_season if per_season > 0 else None


def can_build(bank: int | None, cost: int, cap: int) -> int:
    """How much more the owner needs in the bank to pay for this: 0 when
    they can."""
    if bank is None:
        return cost
    return max(0, round(cap * BALLPARK_FLOOR) + cost - bank)


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
    ballpark: int = 0,
) -> int:
    """Fan interest after a season, with this season's ticket prices and
    marketing department level (None: the defaults), and ballpark points
    (ballpark_fans)."""
    nudge = (
        ticket_fans(ticket_price)
        + (0 if marketing is None else bg.marketing_fans(marketing))
        + ballpark
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
    base = cap / mean * REGULAR_SEASON_BOOST  # league revenue at market 3, fans 50
    return {
        t: Plan(
            revenue=_round(base * pull[t]),
            budget=bg.owner_budget(cap, m.spending, m.bank_change)
            + bg.standard_front_office(cap),
        )
        for t, m in teams.items()
    }


def jersey_money(
    grade: str | None,
    cap: int,
    *,
    all_star: bool = False,
    award: bool = False,
    new: bool = False,
) -> float:
    """What one player's jerseys sell in a season, before his team's market,
    fans and marketing (not rounded: a team adds up its players). A Hall of
    Famer (grade HALL_GRADE) sells retro jerseys; new is his induction."""
    if grade == HALL_GRADE:
        value = HALL_JERSEY * cap / MERCH_CAP
        return value * HALL_INDUCTION if new else value
    value = MERCH_BY_GRADE.get(grade or "", 0) * cap / MERCH_CAP
    if all_star:
        value *= MERCH_ALL_STAR
    if award:
        value *= MERCH_AWARD
    if new:
        value *= MERCH_NEW
    return value


def merch_mult(market: int, fans: float, marketing=None) -> float:
    level = 2 if marketing is None else bg.clean_level(marketing)
    fans = max(0.0, min(100.0, fans))
    return (
        market_mult(market)
        * (MERCH_FAN_LOW + MERCH_FAN_SPAN * fans / 100)
        * MERCH_MARKETING[level]
    )


@dataclass(frozen=True)
class Seller:
    """A player selling jerseys for a team this season."""

    player_id: str
    grade: str | None
    share: float  # of his games, played for this team (1 for a Hall of Famer)
    all_star: bool = False
    award: bool = False
    new: bool = False

    @property
    def hall(self) -> bool:
        return self.grade == HALL_GRADE


def merchandise(
    sellers: list[Seller], cap: int, market: int, fans: float, marketing=None
) -> tuple[int, list[tuple[Seller, int]]]:
    """A team's merchandise money for a season, and each player's part of
    it (best sellers first, players selling nothing left out)."""
    mult = merch_mult(market, fans, marketing)
    parts = []
    for s in sellers:
        value = (
            jersey_money(s.grade, cap, all_star=s.all_star, award=s.award, new=s.new)
            * max(0.0, min(1.0, s.share))
            * mult
        )
        if value > 0:
            parts.append((s, value))
    parts.sort(key=lambda p: -p[1])
    total = _round(sum(v for _, v in parts))
    return total, [(s, _round(v)) for s, v in parts]


def broadcast_years(years) -> int:
    """A deal length, one of BROADCAST_YEARS (the default when unknown)."""
    try:
        years = int(years)
    except TypeError, ValueError:
        return BROADCAST_DEFAULT_YEARS
    return years if years in BROADCAST_YEARS else BROADCAST_DEFAULT_YEARS


def broadcast_appeal(fans: float, win_pct: float) -> float:
    """How much broadcasters want the team, 0 to 1."""
    fan_part = max(0.0, min(100.0, fans)) / 100
    win_part = max(0.0, min(1.0, (win_pct - BROADCAST_WIN_LOW) / BROADCAST_WIN_SPAN))
    return 0.5 * fan_part + 0.5 * win_part


def broadcast_base(
    average_revenue: float, market: int, fans: float, win_pct: float
) -> int:
    """A season of a new broadcast deal at the default length."""
    share = BROADCAST_FLOOR + BROADCAST_SPAN * broadcast_appeal(fans, win_pct)
    return _round(average_revenue * share * market_mult(market))


def broadcast_amount(base: int, years) -> int:
    """A season of a deal this many years long."""
    return _round(base * BROADCAST_LENGTH_MULT[broadcast_years(years)])


def sponsor_steady(average_revenue: float, market: int) -> int:
    """A season of the Steady sponsor deal."""
    return _round(average_revenue * SPONSOR_SHARE * market_mult(market))


def sponsor_kind(kind, last_win_pct: float | None = None) -> str:
    """The deal a team takes: its pick, or by last season's record."""
    if kind in SPONSOR_KINDS:
        return kind
    if last_win_pct is not None and last_win_pct > SPONSOR_AI_FROM:
        return "incentive"
    return "steady"


def sponsor_money(
    steady: int,
    kind: str,
    win_pct: float = 0.5,
    playoffs: bool = False,
    rounds: int = 0,
) -> dict:
    """What a sponsor deal pays for a season, and its parts (Incentive only:
    up front, wins, playoffs, rounds)."""
    if kind != "incentive":
        return {"total": steady, "base": steady, "wins": 0, "playoffs": 0, "rounds": 0}
    parts = {
        "base": _round(steady * SPONSOR_BASE),
        "wins": _round(steady * SPONSOR_PER_WIN_PCT * max(0.0, win_pct - 0.5)),
        "playoffs": _round(steady * SPONSOR_PLAYOFFS) if playoffs else 0,
        "rounds": _round(steady * SPONSOR_PER_ROUND * max(0, rounds)),
    }
    return {"total": sum(parts.values()), **parts}


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
    broadcast: int = 0,
    merchandise: int = 0,
    ballpark: int = 0,
    sponsor: int = 0,
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
    total_in = (
        revenue
        + tickets
        + playoff_gate
        + popularity
        + broadcast
        + merchandise
        + ballpark
        + sponsor
        + tax_share
        + farm_help
    )
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
        "broadcast": broadcast,
        "merchandise": merchandise,
        "ballpark": ballpark,
        "sponsor": sponsor,
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
