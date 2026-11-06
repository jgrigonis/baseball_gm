# src/league/budget.py
"""
The league's payroll cap and each owner's budget (Josh's decisions,
2026-11-05 and 2026-11-06).

The league sets one payroll cap a season, the same for every team: the
league's average payroll the first season budgets are needed, then
CAP_GROWTH more each season after. It's a soft cap: a team can go over
it, and pays a luxury tax on what's over when the season ends. Nothing is
blocked; the game warns before a move that takes a team over.

Each team's owner sets how far from the cap they'll let payroll go, by
their Spending trait: a miser wants payroll under the cap, an owner who
spends to win gives a long leash over it. That's the GM's budget. Going
past it costs no more tax; the owner feels it in their profit, and AI GMs
keep to it. Past a hard limit above the budget, the owner refuses moves
that add money (hard_limit, refusal), for people too.

Each owner has a bank that carries over between seasons. It starts rich,
by their Spending, and the season's profit or loss goes into it. A bank
that's grown loosens the next budget, one that's shrunk tightens it, and
an empty bank pulls the hard limit down to the budget.

Speed Blitz leagues have no budgets (src/league/league_modes.py). The tax
comes off the team's profit, which owners read, and is split among the
teams that stayed under the cap.
"""

from __future__ import annotations

from src.player.contracts import format_salary

# How much the cap grows each season (Josh: "something like 5%").
CAP_GROWTH = 0.05
# Luxury tax: this share of every dollar of payroll over the cap.
LUXURY_TAX_RATE = 0.5
# The first cap rounds to this, so it reads as a round number.
FIRST_CAP_ROUNDING = 5_000_000
# Later caps round to this.
CAP_ROUNDING = 100_000
# The owner's leash, as a share of the cap: LEASH_PER_POINT for every point
# of Spending over LEASH_ZERO. At a $160M cap, Spending 5 (a miser) wants
# about $14M under, 50 allows about $7M over, 95 about $29M over.
LEASH_ZERO = 35
LEASH_PER_POINT = 0.003
LEASH_ROUNDING = 1_000_000
# The owner's bank (Josh, 2026-11-06: "these are rich cats"): it starts at
# the cap times BANK_BASE plus Spending/100, so a miser (5) starts with about
# half a cap and a big spender (95) with about one and a half. Profits and
# losses carry over in it.
BANK_BASE = 0.5
# Each season the budget moves by BANK_PULL of how far the bank is above
# (or below) where it started, at most BANK_SWING of the cap either way.
BANK_PULL = 0.2
BANK_SWING = 0.10
# The owner's hard limit: they refuse moves that add money past their budget
# plus this share of the cap. With the bank empty, the budget is the limit.
HARD_MARGIN = 0.10


def first_cap(payrolls: list[int]) -> int:
    """The league's first cap: its average payroll."""
    if not payrolls:
        return 0
    avg = sum(payrolls) / len(payrolls)
    return max(
        FIRST_CAP_ROUNDING,
        round(avg / FIRST_CAP_ROUNDING) * FIRST_CAP_ROUNDING,
    )


def grown(cap: int, seasons: int = 1) -> int:
    """The cap some seasons later."""
    value = cap * (1 + CAP_GROWTH) ** seasons
    return round(value / CAP_ROUNDING) * CAP_ROUNDING


def salary_scale(seasons: int) -> float:
    """How much contract prices have grown since the league's first cap,
    in step with the cap: new deals are priced off it, so the cap doesn't
    get looser every season (plans/budget.md, Q2). Deals already signed
    keep their numbers."""
    return (1 + CAP_GROWTH) ** max(0, seasons)


def leash(cap: int, spending: int) -> int:
    """How far over the cap (negative: under) an owner with this Spending
    trait lets payroll go."""
    spending = max(0, min(100, spending))
    value = cap * LEASH_PER_POINT * (spending - LEASH_ZERO)
    return round(value / LEASH_ROUNDING) * LEASH_ROUNDING


def owner_budget(cap: int, spending: int, bank_change: int = 0) -> int:
    """The payroll an owner with this Spending trait will stand for, moved
    by how their bank has done since it started."""
    return cap + leash(cap, spending) + bank_adjust(cap, bank_change)


def starting_bank(cap: int, spending: int) -> int:
    """What an owner has in the bank when they start."""
    spending = max(0, min(100, spending))
    value = cap * (BANK_BASE + spending / 100)
    return round(value / LEASH_ROUNDING) * LEASH_ROUNDING


def bank_adjust(cap: int, bank_change: int) -> int:
    """How much a bank that's up (or down) this much since it started moves
    the owner's budget."""
    swing = cap * BANK_SWING
    value = max(-swing, min(swing, bank_change * BANK_PULL))
    return round(value / LEASH_ROUNDING) * LEASH_ROUNDING


def hard_limit(cap: int, budget: int, bank: int | None) -> int:
    """The most payroll an owner will allow: a margin past their budget,
    or just the budget once their bank is empty."""
    if bank is not None and bank <= 0:
        return budget
    margin = round(cap * HARD_MARGIN / LEASH_ROUNDING) * LEASH_ROUNDING
    return budget + margin


def refusal(spend: int, limit: int, added: int) -> str | None:
    """Why the owner refuses a move that adds this much spending, or None
    when it stays inside their hard limit (or takes payroll off)."""
    # spend: payroll plus the front office.
    if added <= 0 or spend + added <= limit:
        return None
    return (
        f"Your owner won't allow it: that takes spending (payroll and front "
        f"office) to {format_salary(spend + added)}, past their "
        f"{format_salary(limit)} limit."
    )


def luxury_tax(payroll: int, cap: int) -> int:
    """The tax on a payroll over the cap (0 when it's under)."""
    return round(max(0, payroll - cap) * LUXURY_TAX_RATE)


def tax_shares(payrolls: dict[str, int], cap: int) -> dict[str, int]:
    """The season's luxury tax, split evenly among the teams that finished
    under the cap (plans/budget.md, Q6). {team_id: share} for those teams;
    empty when nobody paid tax or nobody was under."""
    pool = sum(luxury_tax(p, cap) for p in payrolls.values())
    under = [t for t, p in payrolls.items() if p < cap]
    if not pool or not under:
        return {}
    share = round(pool / len(under) / CAP_ROUNDING) * CAP_ROUNDING
    return {t: share for t in under}


# ── The front office (plans/budget.md, section 7) ───────────────────────────
# Three departments the GM funds out of the owner's budget, each at one of
# five levels, set once each offseason (draft and preseason) and locked for
# the season. Scouting waits for grade fog. Department levels are private.
DEPARTMENTS = (
    ("coaching", "Coaching", "How fast players grow toward their ceilings"),
    ("facilities", "Facilities", "Injuries, time on the IL and wear over a season"),
    ("analytics", "Analytics", "How well your strategy settings are carried out"),
)
DEPARTMENT_KEYS = tuple(d[0] for d in DEPARTMENTS)
LEVELS = ("Bare bones", "Thin", "Standard", "Strong", "Elite")
STANDARD = 2
# Each level's cost a season, as a share of the cap: about $2M, $4M, $6M,
# $9M and $12M at a $160M cap.
LEVEL_SHARE = (0.0125, 0.025, 0.0375, 0.05625, 0.075)
DEPARTMENT_ROUNDING = 100_000


def clean_level(level) -> int:
    try:
        return max(0, min(len(LEVELS) - 1, int(level)))
    except TypeError, ValueError:
        return STANDARD


def level_cost(cap: int, level: int) -> int:
    """What a department at this level costs a season under this cap."""
    value = cap * LEVEL_SHARE[clean_level(level)]
    return round(value / DEPARTMENT_ROUNDING) * DEPARTMENT_ROUNDING


def front_office_cost(cap: int, levels: dict) -> int:
    """The whole front office's cost a season; a missing level is Standard."""
    return sum(level_cost(cap, levels.get(k, STANDARD)) for k in DEPARTMENT_KEYS)


def standard_front_office(cap: int) -> int:
    """A front office at Standard everywhere. Owners' budgets include it,
    and the league's fixed costs are that much lower (src/league/
    finances.py), so a Standard front office leaves the money as it was."""
    return front_office_cost(cap, {})


# What each level does (Bare bones .. Elite).
# Coaching: how fast young players' coachable skills grow toward their
# ceilings (src/player/player_skill_aging.py; the cap doesn't move). Full
# effect at COACHING_FULL_AGE and under, none by COACHING_NO_AGE.
COACHING_GROWTH = (0.85, 0.93, 1.0, 1.08, 1.15)
COACHING_FULL_AGE = 23
COACHING_NO_AGE = 28
# Facilities: the chance of getting hurt, and days out once hurt, for
# hitters and pitchers alike (Josh, 2026-11-06).
FACILITIES_INJURY = (1.15, 1.07, 1.0, 0.93, 0.85)
FACILITIES_DAYS = (1.15, 1.07, 1.0, 0.93, 0.85)


def coaching_growth(level: int, age: int) -> float:
    """The growth multiplier a coaching staff at this level gives a player
    this age: its full effect for the young, fading to none by 28."""
    full = COACHING_GROWTH[clean_level(level)]
    if age <= COACHING_FULL_AGE:
        share = 1.0
    elif age >= COACHING_NO_AGE:
        share = 0.0
    else:
        share = (COACHING_NO_AGE - age) / (COACHING_NO_AGE - COACHING_FULL_AGE)
    return 1.0 + (full - 1.0) * share


def facilities_injury(level: int) -> float:
    return FACILITIES_INJURY[clean_level(level)]


def facilities_days(level: int, days: int) -> int:
    """Days out once hurt, with this level of medical staff and facilities."""
    if days <= 0:
        return days
    return max(1, round(days * FACILITIES_DAYS[clean_level(level)]))


# Analytics: how well a manager's running game is aimed. Each level bends a
# steal or hit and run call toward good spots (a fast runner on a weak arm, a
# contact hitter with a fast runner): the chance is multiplied by the spot's
# quality raised to this power. Bare bones flattens the choice (more tries in
# bad spots, more caught stealing); Elite sharpens it. Standard changes nothing.
ANALYTICS_AIM = (-0.6, -0.3, 0.0, 0.4, 0.8)
SPOT_MIN, SPOT_MAX = 0.4, 2.5


def analytics_aim(level: int, quality: float) -> float:
    """The multiplier for a running-game call in a spot of this quality
    (1.0 = an average spot)."""
    power = ANALYTICS_AIM[clean_level(level)]
    if power == 0.0:
        return 1.0
    return min(SPOT_MAX, max(SPOT_MIN, quality)) ** power


def ai_levels(spending: int, seed: str) -> dict[str, int]:
    """An AI team's levels: a miser owner squeezes the front office, a
    spender funds it, with a little variety per department."""
    import random

    rng = random.Random(seed)
    base = STANDARD + (1 if spending >= 70 else -1 if spending < 30 else 0)
    return {k: clean_level(base + rng.choice((-1, 0, 0, 1))) for k in DEPARTMENT_KEYS}


def _leash_text(cap: int, budget: int) -> str:
    if budget > cap:
        return f"{format_salary(budget - cap)} over the cap"
    if budget < cap:
        return f"{format_salary(cap - budget)} under the cap"
    return "right at the cap"


def standing(
    payroll: int,
    cap: int,
    budget: int,
    limit: int | None = None,
    front_office: int = 0,
) -> dict:
    """A team's payroll against the league's cap, and its spending (payroll
    plus the front office) against its owner's budget and hard limit, for
    the views."""
    limit = hard_limit(cap, budget, None) if limit is None else limit
    spend = payroll + front_office
    # What's left of the budget for payroll once the front office is paid.
    payroll_budget = budget - front_office
    over = max(0, payroll - cap)
    tax = luxury_tax(payroll, cap)
    over_budget = max(0, spend - budget)
    return {
        "payroll": payroll,
        "cap": cap,
        "budget": budget,
        "over": over,
        "over_budget": over_budget,
        "tax": tax,
        "payroll_text": format_salary(payroll),
        "cap_text": format_salary(cap),
        "budget_text": format_salary(budget),
        "payroll_budget": payroll_budget,
        "payroll_budget_text": format_salary(payroll_budget),
        "leash_text": _leash_text(cap, payroll_budget),
        "room_text": format_salary(cap - payroll) if payroll < cap else None,
        "over_text": format_salary(over) if over else None,
        "over_budget_text": format_salary(over_budget) if over_budget else None,
        "budget_room_text": format_salary(budget - spend) if spend < budget else None,
        "tax_text": format_salary(tax) if tax else None,
        "tax_rate": LUXURY_TAX_RATE,
        "limit": limit,
        "limit_text": format_salary(limit),
        "limit_room_text": format_salary(limit - spend) if spend < limit else None,
        "at_limit": spend >= limit,
        "front_office": front_office,
        "front_office_text": format_salary(front_office),
        "spend": spend,
        "spend_text": format_salary(spend),
    }


def warning(
    payroll: int, cap: int, budget: int, added: int, front_office: int = 0
) -> str | None:
    """What to warn a GM about a move that adds this much payroll: luxury
    tax past the league's cap, and the owner's budget (which pays the front
    office too). None when it leaves him under both (or takes payroll
    off)."""
    if added <= 0:
        return None
    after = payroll + added
    parts = []
    extra = luxury_tax(after, cap) - luxury_tax(payroll, cap)
    if extra > 0:
        if payroll > cap:
            parts.append(
                f"You're already over the {format_salary(cap)} cap. "
                f"This adds {format_salary(extra)} more luxury tax."
            )
        else:
            parts.append(
                f"This takes you {format_salary(after - cap)} over the "
                f"{format_salary(cap)} cap: {format_salary(extra)} in "
                "luxury tax."
            )
    if after + front_office > budget:
        if payroll + front_office > budget:
            parts.append("You're already past what your owner will spend.")
        else:
            parts.append(
                f"Your owner won't like it: that's past their "
                f"{format_salary(budget)} budget."
            )
    return " ".join(parts) or None
