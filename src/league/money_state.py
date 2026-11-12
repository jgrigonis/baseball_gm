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
