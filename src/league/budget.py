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
past it costs no more tax, but the owner judges payroll against it
(src/league/owner_scoring.py), and AI GMs keep to it.

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


def owner_budget(cap: int, spending: int) -> int:
    """The payroll an owner with this Spending trait will stand for."""
    return cap + leash(cap, spending)


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


def _leash_text(cap: int, budget: int) -> str:
    if budget > cap:
        return f"{format_salary(budget - cap)} over the cap"
    if budget < cap:
        return f"{format_salary(cap - budget)} under the cap"
    return "right at the cap"


def standing(payroll: int, cap: int, budget: int) -> dict:
    """A team's payroll against the league's cap and its owner's budget,
    for the views."""
    over = max(0, payroll - cap)
    tax = luxury_tax(payroll, cap)
    over_budget = max(0, payroll - budget)
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
        "leash_text": _leash_text(cap, budget),
        "room_text": format_salary(cap - payroll) if payroll < cap else None,
        "over_text": format_salary(over) if over else None,
        "over_budget_text": format_salary(over_budget) if over_budget else None,
        "tax_text": format_salary(tax) if tax else None,
        "tax_rate": LUXURY_TAX_RATE,
    }


def warning(payroll: int, cap: int, budget: int, added: int) -> str | None:
    """What to warn a GM about a move that adds this much payroll: luxury
    tax past the league's cap, and the owner's budget. None when it leaves
    him under both (or takes payroll off)."""
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
    if after > budget:
        if payroll > budget:
            parts.append("You're already past what your owner will spend.")
        else:
            parts.append(
                f"Your owner won't like it: that's past their "
                f"{format_salary(budget)} budget."
            )
    return " ".join(parts) or None
