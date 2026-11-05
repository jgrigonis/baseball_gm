# src/league/budget.py
"""
Team budgets and the luxury tax (Josh's decisions, 2026-11-05).

A team's budget is the payroll its owner will pay for a season. It's a soft
limit: a team can go over, and pays a luxury tax on what's over when the
season ends. Nothing is blocked; the game warns before a move that takes a
team over.

Each team's owner sets its budget, from the revenue its market and fans
bring in and how freely they spend (src/league/finances.py). The league's
average budget is the average payroll the first season budgets are needed,
then BUDGET_GROWTH more each season after. Speed Blitz leagues have no
budgets (src/league/league_modes.py).

The tax comes off the team's profit, which owners read.
"""

from __future__ import annotations

from src.player.contracts import format_salary

# How much a budget grows each season (Josh: "something like 5%").
BUDGET_GROWTH = 0.05
# Luxury tax: this share of every dollar of payroll over budget.
LUXURY_TAX_RATE = 0.5
# The first budget rounds to this, so it reads as a round number.
FIRST_BUDGET_ROUNDING = 5_000_000
# Later budgets round to this.
BUDGET_ROUNDING = 100_000


def first_budget(payrolls: list[int]) -> int:
    """The budget every team starts with: the league's average payroll."""
    if not payrolls:
        return 0
    avg = sum(payrolls) / len(payrolls)
    return max(
        FIRST_BUDGET_ROUNDING,
        round(avg / FIRST_BUDGET_ROUNDING) * FIRST_BUDGET_ROUNDING,
    )


def grown(budget: int, seasons: int = 1) -> int:
    """A budget some seasons later."""
    value = budget * (1 + BUDGET_GROWTH) ** seasons
    return round(value / BUDGET_ROUNDING) * BUDGET_ROUNDING


def luxury_tax(payroll: int, budget: int) -> int:
    """The tax on a payroll over budget (0 when it's under)."""
    return round(max(0, payroll - budget) * LUXURY_TAX_RATE)


def standing(payroll: int, budget: int) -> dict:
    """A team's payroll against its budget, for the views."""
    over = max(0, payroll - budget)
    tax = luxury_tax(payroll, budget)
    return {
        "payroll": payroll,
        "budget": budget,
        "over": over,
        "room": max(0, budget - payroll),
        "tax": tax,
        "payroll_text": format_salary(payroll),
        "budget_text": format_salary(budget),
        "over_text": format_salary(over) if over else None,
        "room_text": format_salary(budget - payroll) if budget > payroll else None,
        "tax_text": format_salary(tax) if tax else None,
        "tax_rate": LUXURY_TAX_RATE,
    }


def warning(payroll: int, budget: int, added: int) -> str | None:
    """What to warn a GM about a move that adds this much payroll, or None
    when it leaves him under budget (or takes payroll off)."""
    if added <= 0:
        return None
    after = payroll + added
    if after <= budget:
        return None
    extra = luxury_tax(after, budget) - luxury_tax(payroll, budget)
    if payroll > budget:
        return (
            f"You're already over budget. This adds {format_salary(added)}, "
            f"and {format_salary(extra)} more luxury tax."
        )
    return (
        f"This takes you {format_salary(after - budget)} over your "
        f"{format_salary(budget)} budget: {format_salary(extra)} in luxury tax."
    )
