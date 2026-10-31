# src/league/hr_derby.py
"""
The Home Run Derby on the All-Star break (plans/all-star-game.md, phase 3).
The pure part: who's in it, the bracket and the swings.
src/api/services/hr_derby.py runs it against the database.

The field. The league's top home run hitters this season, up to FIELD_SIZE,
seeded by home runs (then power). Anyone hurt sits it out and the next man
up takes his place. The field is a power of two, so a small league gets a
smaller bracket, and fewer than two hitters means no derby.

The bracket. One on one, seeds 1 v 8, 4 v 5, 2 v 7 and 3 v 6, the winners
meeting until two are left for the final.

A round. The hitter swings until he's made OUTS_PER_ROUND outs: any swing
that isn't a home run is an out. Each swing is a home run with
hr_chance(power, contact). The lower seed hits first. A tie goes to a
swing-off: SWINGOFF_SWINGS swings each, again until someone's ahead.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

FIELD_SIZE = 8
OUTS_PER_ROUND = 10
SWINGOFF_SWINGS = 3
# Swing-offs before the higher seed goes through, so a round always ends.
MAX_SWINGOFFS = 20
# The derby is on this day of the break (the first is 1).
DAY_OF_BREAK = 2

ROUND_NAMES = {1: "Final", 2: "Semifinals", 4: "Quarterfinals"}


def derby_date(w) -> str:
    """The day of the derby: the second day of the break, or the last day
    before play resumes if the break is shorter."""
    closes = date.fromisoformat(w.closes)
    resumes = date.fromisoformat(w.resumes)
    day = min(closes + timedelta(days=DAY_OF_BREAK), resumes - timedelta(days=1))
    return day.isoformat()


def field(hitters: list[dict], hurt: set) -> list[dict]:
    """The field, best seed first: [{player_id, ..., seed}], from hitters
    ({player_id, name, bat_home_runs, power, ...}). Only players with a home
    run count, and nobody hurt."""
    able = [h for h in hitters if h["bat_home_runs"] > 0 and h["player_id"] not in hurt]
    able.sort(key=lambda h: (-h["bat_home_runs"], -h["power"], h["name"]))
    size = 1
    while size * 2 <= min(FIELD_SIZE, len(able)):
        size *= 2
    if size < 2:
        return []
    return [{**h, "seed": i} for i, h in enumerate(able[:size], 1)]


def first_round(size: int) -> list[tuple[int, int]]:
    """The first round's matchups by seed, in bracket order, so neighbours
    meet next: 1 v 8, 4 v 5, 2 v 7, 3 v 6 for 8."""
    order = [1]
    while len(order) < size:
        n = len(order) * 2 + 1
        order = [s for seed in order for s in (seed, n - seed)]
    return [(order[i], order[i + 1]) for i in range(0, size, 2)]


def round_name(players_left: int) -> str:
    return ROUND_NAMES.get(players_left // 2, f"Round of {players_left}")


def hr_chance(power: float, contact: float) -> float:
    """The chance a batting practice swing goes out: mostly power, a little
    contact."""
    p = 0.30 + 0.40 * power / 100 + 0.05 * (contact - 50) / 50
    return min(0.75, max(0.20, p))


def distance(power: float, rng: random.Random) -> int:
    """How far a home run goes, in feet."""
    return round(375 + 60 * power / 100 + rng.gauss(0, 18))


def swings(h: dict, rng: random.Random, outs: int | None = None, n: int | None = None):
    """A hitter's turn: until `outs` outs, or for `n` swings. Returns
    (home runs, longest)."""
    p = hr_chance(h["power"], h["contact"])
    homers = made = taken = longest = 0
    while (outs is None or made < outs) and (n is None or taken < n):
        taken += 1
        if rng.random() < p:
            homers += 1
            longest = max(longest, distance(h["power"], rng))
        else:
            made += 1
    return homers, longest


def matchup(high: dict, low: dict, rng: random.Random) -> list[dict]:
    """One on one: the lower seed hits first. Returns both lines, {player_id,
    homers, swingoff (None without one), longest, won}, high seed first."""
    lines = {}
    for h in (low, high):
        homers, longest = swings(h, rng, outs=OUTS_PER_ROUND)
        lines[h["player_id"]] = {"homers": homers, "swingoff": None, "longest": longest}
    a, b = lines[high["player_id"]], lines[low["player_id"]]
    tries = 0
    while a["homers"] + (a["swingoff"] or 0) == b["homers"] + (b["swingoff"] or 0):
        tries += 1
        if tries > MAX_SWINGOFFS:
            break
        for h, line in ((low, b), (high, a)):
            homers, longest = swings(h, rng, n=SWINGOFF_SWINGS)
            line["swingoff"] = (line["swingoff"] or 0) + homers
            line["longest"] = max(line["longest"], longest)
    high_wins = a["homers"] + (a["swingoff"] or 0) >= b["homers"] + (b["swingoff"] or 0)
    return [
        {"player_id": high["player_id"], **a, "won": high_wins},
        {"player_id": low["player_id"], **b, "won": not high_wins},
    ]


def run(entrants: list[dict], rng: random.Random) -> list[dict]:
    """The whole derby for a field (field()): every matchup's two lines,
    {round, match, player_id, seed, homers, swingoff, longest, won}, round
    1 first. The last match's winner is the champion."""
    by_seed = {h["seed"]: h for h in entrants}
    pairs = [(by_seed[a], by_seed[b]) for a, b in first_round(len(entrants))]
    out = []
    rnd = 1
    while pairs:
        winners = []
        for match, (high, low) in enumerate(pairs, 1):
            for line in matchup(high, low, rng):
                h = high if line["player_id"] == high["player_id"] else low
                out.append({"round": rnd, "match": match, "seed": h["seed"], **line})
                if line["won"]:
                    winners.append(h)
        # The better seed stays "high", so he hits second.
        pairs = [
            tuple(sorted(winners[i : i + 2], key=lambda h: h["seed"]))
            for i in range(0, len(winners) - 1, 2)
        ]
        rnd += 1
    return out
