# src/league/swing_off.py
"""
The home run swing-off that settles an All-Star or Rookie Game still tied
after nine innings, as in MLB's All-Star Game. The pure part: who hits and
the swings. src/api/services/all_star.py plays it after the game.

Each side sends up its HITTERS best home run hitters (by hr_derby's
hr_chance), who get SWINGS swings each, in batting practice as at the
Derby. The away side (side 2) hits first. Most home runs wins. Still tied,
it's sudden death: one swing each, the same hitters taking turns, until one
side homers and the other doesn't.
"""

from __future__ import annotations

import random

from src.league.hr_derby import hr_chance, swings

HITTERS = 3
SWINGS = 3
# Sudden-death rounds before the home side is given it, so it always ends.
MAX_ROUNDS = 50
# Side 2 is the away side in the All-Star and Rookie Games.
ORDER = (2, 1)


def hitters(players: list[dict], n: int = HITTERS) -> list[dict]:
    """A side's swing-off hitters, best first, from {player_id, name, power,
    contact}."""
    return sorted(
        players, key=lambda h: (-hr_chance(h["power"], h["contact"]), h["name"])
    )[:n]


def play(sides: dict[int, list[dict]], rng: random.Random) -> dict:
    """The swing-off between sides {1: hitters, 2: hitters}. Returns
    {"winner": side, "1": lines, "2": lines, "sudden_death": rounds}: each
    line {player_id, name, homers}, each sudden-death round {"1": homered,
    "2": homered}."""
    out: dict = {"sudden_death": []}
    for side in ORDER:
        out[str(side)] = [
            {
                "player_id": h["player_id"],
                "name": h["name"],
                "homers": swings(h, rng, n=SWINGS)[0],
            }
            for h in sides[side]
        ]
    score = {s: sum(line["homers"] for line in out[str(s)]) for s in ORDER}
    i = 0
    while score[1] == score[2] and i < MAX_ROUNDS:
        rnd = {}
        for side in ORDER:
            line = sides[side]
            homered = bool(line) and swings(line[i % len(line)], rng, n=1)[0] == 1
            rnd[str(side)] = homered
            score[side] += homered
        out["sudden_death"].append(rnd)
        i += 1
    out["winner"] = 2 if score[2] > score[1] else 1
    return out


def total(result: dict, side: int) -> int:
    """A side's home runs in the swing-off, sudden death and all."""
    return sum(line["homers"] for line in result[str(side)]) + sum(
        1 for rnd in result["sudden_death"] if rnd[str(side)]
    )


def winner(g: dict) -> int:
    """The side that won an All-Star or Rookie Game row: the swing-off's
    winner if there was one, otherwise whoever scored more."""
    if g.get("swingoff"):
        return g["swingoff"]["winner"]
    return 1 if (g["score1"] or 0) > (g["score2"] or 0) else 2
