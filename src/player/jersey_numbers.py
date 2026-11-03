# src/player/jersey_numbers.py
"""
Jersey numbers.

Every player is born with a list of numbers he'd like to wear: a favorite
first, then a few fallbacks if it's taken (often the favorite's cousins: 7
becomes 17, 27 or 77). The list is stored on the player (players.jersey_prefs)
and never changes.

The number he wears belongs to his spot on a team (team_players.jersey_number)
and no two players on a team share one. When he joins a team he takes the
first number on his list nobody is wearing. If a number is held, seniority
wins and he moves down his list, except that an aging veteran may hand his
number to a star who just arrived and take one of his own fallbacks.

Pure rules only; src/db/repositories/jersey_repo.py does the reading and
writing.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Collection

# How much players want each number. Follows the "most productive uniform
# numbers in MLB history" curve (career WAR by number): the single digits and
# teens are the most popular, the 20s close behind, a slide through the 30s
# and 40s, and almost nobody past 60. 13 keeps its real-life dip. 42 isn't
# retired in this league, so it sits with its neighbours instead of at the
# retired-number low the real chart shows.
NUMBER_WEIGHTS: dict[str, int] = {
    "0": 40, "00": 10,
    "1": 1550, "2": 1520, "3": 1610, "4": 1690, "5": 2000,
    "6": 1880, "7": 1840, "8": 1560, "9": 1640, "10": 1690,
    "11": 1840, "12": 1510, "13": 990, "14": 1480, "15": 1760,
    "16": 1650, "17": 1600, "18": 1490, "19": 1670, "20": 1490,
    "21": 1760, "22": 1690, "23": 1600, "24": 1840, "25": 1720,
    "26": 1130, "27": 1500, "28": 1530, "29": 1380, "30": 1330,
    "31": 1310, "32": 1120, "33": 1240, "34": 1130, "35": 1200,
    "36": 1110, "37": 910, "38": 820, "39": 840, "40": 870,
    "41": 1000, "42": 900, "43": 790, "44": 1090, "45": 810,
    "46": 770, "47": 710, "48": 800, "49": 760, "50": 510,
    "51": 550, "52": 350, "53": 400, "54": 340, "55": 490,
    "56": 290, "57": 280, "58": 210, "59": 140, "60": 70,
    "61": 120, "62": 90, "63": 60, "64": 30, "65": 70,
    "66": 50, "67": 30, "68": 30, "69": 5, "70": 20,
    "71": 20, "72": 40, "73": 20, "74": 30, "75": 60,
    "76": 5, "77": 25, "78": 3, "79": 30, "80": 5,
    "81": 10, "82": 5, "83": 5, "84": 10, "85": 10,
    "86": 5, "87": 3, "88": 15, "89": 8, "90": 8,
    "91": 10, "92": 5, "93": 5, "94": 10, "95": 8,
    "96": 10, "97": 12, "98": 5, "99": 80,
}  # fmt: skip

NUMBERS: tuple[str, ...] = tuple(NUMBER_WEIGHTS)

# Favorite plus this many fallbacks.
FALLBACKS = 5

# A fallback that shares the favorite's last digit (7 → 17, 27) or is the
# favorite doubled (7 → 77) or reversed (24 → 42) is this much likelier.
COUSIN_BOOST = 6

# Who hands his number over: a veteran this old, to a newcomer who is a star
# (about an A- or better), one of the best few players on his new team and
# clearly better than the veteran.
VETERAN_AGE = 33
STAR_RATING = 68
STAR_TEAM_RANK = 3
STAR_MARGIN = 8
DEFER_CHANCE = 0.6


def sort_key(number: str) -> tuple[int, int]:
    """Jersey order: 0, 00, 1, 2, ... 99."""
    return (int(number), len(number))


def _cousins(favorite: str) -> set[str]:
    out: set[str] = set()
    last = favorite[-1]
    for n in NUMBERS:
        if n != favorite and n[-1] == last and len(n) == 2 and n != "00":
            out.add(n)
    if len(favorite) == 1:
        out.add(favorite * 2)
    elif favorite[0] != favorite[1]:
        flipped = favorite[::-1].lstrip("0") or "0"
        out.add(flipped)
    out.discard(favorite)
    return out & set(NUMBERS)


def _weighted_pick(
    rng: random.Random, weights: dict[str, float], exclude: Collection[str] = ()
) -> str | None:
    choices = [(n, w) for n, w in weights.items() if n not in exclude and w > 0]
    if not choices:
        return None
    total = sum(w for _, w in choices)
    r = rng.random() * total
    for n, w in choices:
        r -= w
        if r < 0:
            return n
    return choices[-1][0]


def random_prefs(rng: random.Random, fallbacks: int = FALLBACKS) -> list[str]:
    """A favorite drawn from the curve, then fallbacks that lean toward its
    cousins."""
    favorite = _weighted_pick(rng, NUMBER_WEIGHTS)
    prefs = [favorite]
    cousins = _cousins(favorite)
    weights = {
        n: w * (COUSIN_BOOST if n in cousins else 1) for n, w in NUMBER_WEIGHTS.items()
    }
    while len(prefs) < fallbacks + 1:
        prefs.append(_weighted_pick(rng, weights, exclude=prefs))
    return prefs


def prefs_for(player_id: str) -> list[str]:
    """The player's list, seeded by his id so it's the same every time it's
    made (at creation, or when an older player is backfilled)."""
    return random_prefs(random.Random(f"jersey:{player_id}"))


def clean_prefs(prefs, player_id: str) -> list[str]:
    """The stored list, or a fresh one if there isn't a usable one."""
    good = [str(n) for n in prefs or () if str(n) in NUMBER_WEIGHTS]
    return good or prefs_for(player_id)


def open_number(prefs: list[str], taken: Collection[str], rng: random.Random) -> str:
    """The first number on the list nobody is wearing, or, if every one is
    taken, a free number drawn from the curve."""
    for n in prefs:
        if n not in taken:
            return n
    pick = _weighted_pick(rng, NUMBER_WEIGHTS, exclude=taken)
    if pick is None:  # all 101 taken, which a roster never reaches
        raise ValueError("no jersey numbers left")
    return pick


def choose_number(
    prefs: list[str],
    holders: dict[str, str],
    rng: random.Random,
    will_defer: Callable[[str], bool] = lambda _holder: False,
) -> tuple[str, str | None]:
    """
    The number a newcomer gets, and who (if anyone) gives it up.

    holders maps each number worn on the team to the player wearing it.
    Walking down his list, a free number is his. A held one stays with its
    holder (seniority) unless will_defer(holder) says that player hands it
    over; then the newcomer takes it and the holder has to pick again.
    """
    for n in prefs:
        holder = holders.get(n)
        if holder is None:
            return n, None
        if will_defer(holder):
            return n, holder
    return open_number(prefs, holders, rng), None


def defers(
    *,
    holder_age: int,
    holder_rating: int,
    newcomer_rating: int,
    newcomer_team_rank: int,
    rng: random.Random,
) -> bool:
    """Does an aging veteran give his number to a star who just arrived?"""
    if holder_age < VETERAN_AGE:
        return False
    if newcomer_rating < STAR_RATING or newcomer_team_rank > STAR_TEAM_RANK:
        return False
    if newcomer_rating < holder_rating + STAR_MARGIN:
        return False
    return rng.random() < DEFER_CHANCE


def assign_by_seniority(
    players: list[tuple[str, list[str]]], rng: random.Random
) -> dict[str, str]:
    """Numbers for a whole roster at once, most senior first: each takes the
    first open number on his list. players is (player_id, prefs) in order."""
    out: dict[str, str] = {}
    taken: set[str] = set()
    for pid, prefs in players:
        n = open_number(prefs, taken, rng)
        out[pid] = n
        taken.add(n)
    return out
