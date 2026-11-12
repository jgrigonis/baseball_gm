# src/api/services/records/core.py
"""
The shapes every record shares, and how a list of performances becomes a
record card: the holders at the top, then the next best.

A performance is a dict with at least ``value`` (what's compared), ``shown``
(how it's printed) and ``order`` (first to get there sorts first: a date or
year). The rest (player_id, name, team, year, note, active, is_mine) is
passed through to the page.

Ties: everyone at the top value holds the record, the first to reach it
listed first. A card shows the holders and then the next best, five rows in
all, with ties for a place sharing its rank.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LIST_SIZE = 5
HOLDERS_SHOWN = 3
MORE_SHOWN = 30  # names behind "+N more tied"


@dataclass
class Card:
    key: str
    label: str
    tip: str = ""
    lower: bool = False  # lower is better (ERA, WHIP, fewest wins)
    rows: list[dict] = field(default_factory=list)  # ranked, holders first
    holders: list[dict] = field(default_factory=list)
    mark: dict | None = None  # an unbeaten league mark (a floor), no holder
    times: int = 0  # how often the record value was reached (single games)
    note: str = ""  # the qualifier, under the title
    listing: bool = False  # a top ten with no headline record

    @property
    def more_holders(self) -> int:
        return max(0, len(self.holders) - len(self.shown_holders))

    @property
    def crowded(self) -> bool:
        """Tied so often it's shown as the first, the latest and a count."""
        return len(self.holders) > HOLDERS_SHOWN

    @property
    def shown_holders(self) -> list[dict]:
        if self.crowded:
            latest = max(self.holders, key=lambda h: h.get("order") or "")
            return [self.holders[0], latest]
        return self.holders[:HOLDERS_SHOWN]

    @property
    def hidden_holders(self) -> list[dict]:
        shown = {id(h) for h in self.shown_holders}
        return [h for h in self.holders if id(h) not in shown][:MORE_SHOWN]

    @property
    def others(self) -> list[dict]:
        """The rows after the holders."""
        return self.rows[len(self.holders) :]

    @property
    def empty(self) -> bool:
        return not self.rows and not self.mark


def sort_key(p: dict, lower: bool):
    v = p["value"]
    return (v if lower else -v, p.get("order") or "", p.get("name") or "")


def rank(perfs: list[dict], lower: bool = False, size: int = LIST_SIZE) -> list[dict]:
    """The best ``size`` performances, ranked: ties share a rank (1, 2, 2,
    4). Everyone tied for first is kept even past ``size``."""
    ordered = sorted(perfs, key=lambda p: sort_key(p, lower))
    out: list[dict] = []
    for i, p in enumerate(ordered):
        tied_prev = out and out[-1]["value"] == p["value"]
        if i >= size and not (tied_prev and out[-1]["rank"] == 1):
            break
        p = dict(p)
        p["rank"] = out[-1]["rank"] if tied_prev else i + 1
        out.append(p)
    return out


def card(
    key: str,
    label: str,
    perfs: list[dict],
    *,
    lower: bool = False,
    tip: str = "",
    note: str = "",
    floor: float | None = None,
    floor_shown: str = "",
    size: int = LIST_SIZE,
    listing: bool = False,
) -> Card:
    """A record card from every performance that could be on it.

    ``floor`` is the league mark a new league starts with: until somebody
    beats it (a tie doesn't count), the card's record is that mark, with
    nobody holding it, and the best performances so far are listed under it.
    """
    rows = rank(perfs, lower, size)
    holders = [r for r in rows if r["rank"] == 1]
    c = Card(key, label, tip=tip, lower=lower, rows=rows, note=note, listing=listing)
    if floor is not None and not _beats(holders, floor, lower):
        c.mark = {"value": floor, "shown": floor_shown or _plain(floor)}
        c.holders = []
        c.rows = rows[:size]
    else:
        c.holders = holders
        top = holders[0]["value"] if holders else None
        c.times = sum(1 for p in perfs if p["value"] == top) if holders else 0
    return c


def _beats(holders: list[dict], floor: float, lower: bool) -> bool:
    if not holders:
        return False
    v = holders[0]["value"]
    return v < floor if lower else v > floor


def _plain(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v}"


def rate3(v: float) -> str:
    """.345 style, 1.000 kept."""
    s = f"{v:.3f}"
    return s[1:] if s.startswith("0") else s


def rate2(v: float) -> str:
    return f"{v:.2f}"
