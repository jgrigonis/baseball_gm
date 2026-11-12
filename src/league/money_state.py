# src/league/money_state.py
"""
Money states: where a team stands with its owner's money, in a word, and so
how its front office spends (plans/ai-gm-strategy.md, section 7, "capped out"
and "cutting costs"; plans/budget.md 4.5).

    flush          lots of room under the owner's budget, and a healthy bank
    balanced       some room
    capped-out     little or no room, or an owner's bank running low
    cutting-costs  spending past the owner's budget, or the bank is empty

It's worked out from the books whenever it's needed, never stored: the room
the owner's budget leaves for payroll (src/league/budget.py standing,
budget_payroll_room, which counts the luxury tax, the front office and the
minor leagues), as a share of the league's cap so it means the same as the
cap grows, and the owner's bank against where it started.

What reads it (AI teams only; a person just sees the word):
- Trades: how much an AI team charges against a player's contract
  (src/league/trades/ai_evaluator.py money_share). A team cutting costs also
  goes looking for deals that lower its payroll (src/api/services/ai_trades.py).
- Free agents and waivers (src/api/services/ai_free_agents.py,
  src/api/services/offseason_fa.py): a flush team signs a smaller upgrade, a
  capped-out one only bargains, one cutting costs only minimum deals.
"""

from __future__ import annotations

STATES = ("flush", "balanced", "capped-out", "cutting-costs")

LABELS = {
    "flush": "Flush",
    "balanced": "Balanced",
    "capped-out": "Capped out",
    "cutting-costs": "Cutting costs",
}

# What each one means, for the tag's tooltip.
TIPS = {
    "flush": "Lots of room under the owner's budget: happy to take on salary",
    "balanced": "Some room under the owner's budget",
    "capped-out": "Little or no room under the owner's budget: only bargains",
    "cutting-costs": "Spending past the owner's budget: looking to shed salary",
}

# Room under the owner's budget, as a share of the cap. Past the budget by
# more than CUTTING_ROOM is cutting costs (a hair over is only capped out);
# under CAPPED_ROOM is capped out; FLUSH_ROOM or more is flush.
CUTTING_ROOM = -0.05
CAPPED_ROOM = 0.04
FLUSH_ROOM = 0.18
# An owner's bank under this share of where it started keeps the team from
# spending more than a capped-out one; an empty bank is cutting costs. A
# flush team's bank has to be at least where it started.
LOW_BANK = 0.25

# The share of a player's fair pay an AI team charges against him in a
# trade (ai_evaluator.money_share), by money state.
MONEY_SHARE = {
    "flush": 0.2,
    "balanced": 0.4,
    "capped-out": 0.55,
    "cutting-costs": 0.6,
}

# Free agents: a flush team signs someone this many rating points less of
# an upgrade than the usual hole margin.
FLUSH_MARGIN_CUT = 2


def classify(
    room: int, cap: int, bank: int | None = None, bank_start: int | None = None
) -> str:
    """The money state for this much room under the owner's budget (negative:
    over it) and their bank (None: no bank, e.g. before banks came in)."""
    share = room / cap if cap > 0 else 0.0
    if bank is not None and bank <= 0:
        return "cutting-costs"
    if share < CUTTING_ROOM:
        return "cutting-costs"
    low_bank = bank is not None and bank_start and bank < LOW_BANK * bank_start
    if share < CAPPED_ROOM or low_bank:
        return "capped-out"
    rich = bank is None or not bank_start or bank >= bank_start
    if share >= FLUSH_ROOM and rich:
        return "flush"
    return "balanced"


def label(state: str | None) -> str:
    return LABELS.get(state or "", "")


def money_share(state: str | None) -> float:
    """The share of fair pay charged against a player in a trade."""
    return MONEY_SHARE.get(state or "", MONEY_SHARE["balanced"])


def hole_margin(state: str | None, margin: float) -> float:
    """How much of an upgrade a free agent has to be for this team."""
    if state == "flush":
        return max(1, margin - FLUSH_MARGIN_CUT)
    return margin


def may_sign(state: str | None, salary: int, minimum: int, bargain: bool) -> bool:
    """Whether a team in this state signs a player for this salary: one
    cutting costs only at the minimum, a capped-out one only a bargain (or
    the minimum)."""
    if state == "cutting-costs":
        return salary <= minimum
    if state == "capped-out":
        return bargain or salary <= minimum
    return True


def sheds(state: str | None) -> bool:
    """Whether a team goes looking for deals that lower its payroll."""
    return state == "cutting-costs"


# People run their own teams' money, so the AI states above mean little for
# them: a person's team shows where its payroll and spending stand instead,
# best to worst (src/api/view_models/standings.py). Over the owner's limit
# happens when re-signing their own players (the bank covers it).
PAYROLL_STATES = ("under-cap", "over-cap", "over-budget", "over-limit")

PAYROLL_LABELS = {
    "under-cap": "Under cap",
    "over-cap": "Over cap",
    "over-budget": "Over budget",
    "over-limit": "Over limit",
}


def payroll_state(standing: dict | None) -> str | None:
    """Where a team's money stands for a person's team, from
    src/league/budget.py standing(): past the owner's hard limit, past
    their budget, payroll over the cap, or under it. None without budgets."""
    if not standing:
        return None
    if standing.get("over_limit_text"):
        return "over-limit"
    if standing.get("over_budget"):
        return "over-budget"
    if standing.get("over"):
        return "over-cap"
    return "under-cap"


def payroll_tip(state: str | None, standing: dict | None) -> str:
    """The tag's tooltip: the numbers behind it."""
    if not state or not standing:
        return ""
    s = standing
    if s.get("over_text"):
        payroll = f"Payroll {s['payroll_text']}, {s['over_text']} over the {s['cap_text']} cap"
    else:
        payroll = f"Payroll {s['payroll_text']}, under the {s['cap_text']} cap"
    if state == "over-limit":
        spend = (
            f"total spending {s['spend_text']}, {s['over_limit_text']} past the "
            f"owner's {s['limit_text']} limit"
        )
    elif state == "over-budget":
        spend = (
            f"total spending {s['spend_text']}, {s['over_budget_text']} past the "
            f"owner's {s['budget_text']} budget"
        )
    else:
        spend = (
            f"total spending {s['spend_text']}, within the owner's "
            f"{s['budget_text']} budget"
        )
    return f"{payroll}; {spend}"


# AI teams offering a trade to a person's team keep to that team's money
# too, so they don't send offers its owner would refuse or hate
# (src/api/services/ai_trades.py): nothing that adds salary once it's past
# the owner's limit, close to even (EVEN_SHARE of the cap) once past the
# budget, and otherwise up to what the budget leaves plus that much.
EVEN_SHARE = 0.02


def person_pay_room(standing: dict | None) -> int | None:
    """How much more payroll an AI team's offer may add to a person's team,
    from src/league/budget.py standing(); None without budgets."""
    if not standing:
        return None
    limit_room = standing["limit_payroll_room"]
    if limit_room <= 0 or standing.get("over_limit_text"):
        return 0
    even = round(EVEN_SHARE * standing["cap"])
    return max(0, min(limit_room, max(0, standing["budget_payroll_room"]) + even))
