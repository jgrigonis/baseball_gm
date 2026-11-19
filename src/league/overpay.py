"""
Overpaying a player: a salary well past his market price (Josh, 2026-11-19:
"Signing an F rated 19 year old for 30 million didn't even make the Owner
flinch"). Two levels, against his full asking price (his market value,
before any in-season discount; the minimum for a fringe player):

- "over": at least OVER_SHARE times his price and OVER_EXTRA a season more.
  Owners who watch the money (profit weight or a miser's spending) and
  meddlers say something.
- "egregious": at least EGREGIOUS_SHARE times his price and EGREGIOUS_EXTRA a
  season more. Every owner says something.

The dollar lines grow with the league's cap (scale: src/league/budget.py
salary_scale). Used for the warning before an offer or bid goes in, the
owner's reaction to the signing, and the rare complaint about an overpaid
player already on the roster (src/api/services/owner_office.py). Nothing
here blocks a signing.
"""

from __future__ import annotations

from src.league import owners
from src.player.contracts import format_salary

OVER_SHARE = 1.5
OVER_EXTRA = 3_000_000
EGREGIOUS_SHARE = 3.0
EGREGIOUS_EXTRA = 10_000_000

# Meddling at this level or more: an opinion on every overpay (as with
# trades, src/league/owner_messages.py MEDDLES).
MEDDLES = 70
# Spending at this level or less: a miser, who minds an overpay.
MISER = 30
# Spending at this level or more: an owner who spends to win (Tycoons,
# Showmen), who goes easier on an overpay.
SPENDER = 80

# How far the owner's mood moves at a signing, before temper (-1 to 1
# scale), and a season more of the deal past the first for an egregious one,
# up to EGREGIOUS_MOST.
OVER_MOOD = -0.05
EGREGIOUS_MOOD = -0.12
EGREGIOUS_PER_YEAR = -0.03
EGREGIOUS_MOST = -0.3
# The rare complaint about a player already on the roster.
COMPLAINT_MOOD = -0.05


def level(salary: int, fair: int, scale: float = 1.0) -> str | None:
    """ "egregious", "over" or None: how far salary is past fair, his market
    price, both a season."""
    fair = max(1, int(fair))
    extra = salary - fair
    if salary >= EGREGIOUS_SHARE * fair and extra >= EGREGIOUS_EXTRA * scale:
        return "egregious"
    if salary >= OVER_SHARE * fair and extra >= OVER_EXTRA * scale:
        return "over"
    return None


def times(salary: int, fair: int) -> str:
    """How many times his price, in words for the warning: "twice",
    "about 4 times", "about 38 times"."""
    n = salary / max(1, fair)
    if n < 2.25:
        return "about twice" if n >= 1.75 else "half again"
    return f"about {round(n)} times"


def warning(salary: int, fair: int, scale: float = 1.0) -> str | None:
    """The line before an offer or bid goes in, when it overpays him."""
    how = level(salary, fair, scale)
    if how is None:
        return None
    extra = format_salary(salary - fair)
    head = (
        f"He's asking {format_salary(fair)} a season. {format_salary(salary)} is "
        f"{extra} a season more, {times(salary, fair)} his price."
    )
    if how == "egregious":
        return head + " Every owner notices money like that, and yours will."
    return head + " An owner who watches the money will notice."


def cares(owner: dict, how: str | None) -> bool:
    """Whether this owner says something about an overpay this big: every
    owner at egregious; money-minded owners and meddlers at over."""
    if how == "egregious":
        return True
    if how != "over":
        return False
    w = owners.clean_weights(owner.get("weights") or {})
    t = owners.clean_traits(owner.get("traits") or {})
    return (
        w["profit"] >= owners.STRONG
        or t["spending"] <= MISER
        or t["meddling"] >= MEDDLES
    )


def mood(owner: dict, how: str, years: int) -> float:
    """How far a signing this far over moves the owner's mood: more for a
    long egregious deal, half as much from an owner who spends to win."""
    if how == "egregious":
        delta = max(
            EGREGIOUS_MOST, EGREGIOUS_MOOD + EGREGIOUS_PER_YEAR * (max(1, years) - 1)
        )
    else:
        delta = OVER_MOOD
    if owners.clean_traits(owner.get("traits") or {})["spending"] >= SPENDER:
        delta /= 2
    return delta


def voice(owner: dict) -> str:
    """Which wording an owner uses: "spender" (shrugs it off a bit), "money"
    (counts every dollar) or "plain"."""
    w = owners.clean_weights(owner.get("weights") or {})
    t = owners.clean_traits(owner.get("traits") or {})
    if t["spending"] >= SPENDER:
        return "spender"
    if w["profit"] >= owners.STRONG or t["spending"] <= MISER:
        return "money"
    return "plain"
