# src/league/rookie_game.py
"""
The Rookie Game on the All-Star break (plans/all-star-game.md, phase 4). The
pure part: who's in it and who runs it. src/api/services/rookie_game.py
picks them against the database; the draft and the game are the All-Star
Game's (src/api/services/all_star.py with event="rookie").

The pool. The season's rookies who aren't All-Stars and aren't hurt, picked
by the stat score the All-Star ballot starts from, with no vote. A rookie
needs PLAYING_TIME_SHARE of the playing time an All-Star does. Like the
All-Stars, the pool is two teams' worth, smaller:

    the top 2 at each of the 8 fielding positions     16
    the top 2 DHs                                       2
    the top 16 pitchers                                16
    wildcards: the best left, any position              6

A league with too few rookies to field two sides (MIN_HITTERS hitters and
MIN_PITCHERS pitchers) has no Rookie Game that year.

The captains. The GMs of the two teams with the most rookies in the pool,
apart from the All-Star Game's captains, so somebody else gets a turn.
Ties go to the better record, and captain 1, the one with more rookies, is
the home side and picks first. A league too small for two other teams with
a rookie in the pool goes back to everyone.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.league import all_star
from src.league.all_star import FIELD_SLOTS

QUOTA = {**dict.fromkeys(FIELD_SLOTS, 2), "dh": 2, "p": 16}
POOL_SIZE = 40
# An AI captain's needs for a side of 20.
SIDE_NEEDS = {**dict.fromkeys(FIELD_SLOTS, 1), "dh": 1, "p": 8}
# The share of an All-Star's playing time a rookie needs to be picked.
PLAYING_TIME_SHARE = 0.5
MIN_HITTERS = 18
MIN_PITCHERS = 4
# The game is on this day of the break (the first is 1).
DAY_OF_BREAK = 1


def pool(cands: list[dict], rookie_ids: set, left_out: set) -> list[dict]:
    """The Rookie Game's players, rows as all_star.select_pool's, from the
    ballot's candidates (all_star.add_features): the best rookies not in
    left_out (the All-Stars and anyone hurt). Empty when there aren't
    enough for two sides."""
    rookies = [
        c
        for c in cands
        if c["player_id"] in rookie_ids and c["player_id"] not in left_out
    ]
    if not rookies:
        return []
    rows = all_star.select_pool(rookies, {}, QUOTA, POOL_SIZE)
    pitchers = sum(1 for r in rows if r["slot"] == "p")
    if pitchers < MIN_PITCHERS or len(rows) - pitchers < MIN_HITTERS:
        return []
    return rows


def captains(rows: list[dict], standings: list[str], all_star_captains) -> list[str]:
    """The two captains' team ids, captain 1 first, from the pool and the
    team ids in standings order. Empty if there aren't two teams."""
    count: dict[str, int] = {}
    for r in rows:
        count[r["team_id"]] = count.get(r["team_id"], 0) + 1
    others = [t for t in standings if t not in set(all_star_captains or ())]
    if sum(1 for t in others if count.get(t)) < 2:
        others = list(standings)
    rank = {t: i for i, t in enumerate(standings)}
    others.sort(key=lambda t: (-count.get(t, 0), rank[t]))
    return others[:2] if len(others) >= 2 else []


def game_date(w: all_star.Window) -> str:
    """The day of the Rookie Game: the first day of the break."""
    closes = date.fromisoformat(w.closes)
    resumes = date.fromisoformat(w.resumes)
    day = min(closes + timedelta(days=DAY_OF_BREAK), resumes - timedelta(days=1))
    return day.isoformat()
