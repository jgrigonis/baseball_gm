# src/league/power_rankings.py
#
# Team strength for the Power Rankings page: how good each roster is at
# hitting, pitching and defense, weighted by what the game engine actually
# rewards, then blended with how the team has played (run differential) as
# the season goes on.
#
# The weights come from 12 simulated 30-team, 162-game seasons (Nov 2026):
# - Pitching: control (accuracy) is the biggest single driver of runs
#   allowed, about -0.74 runs per 9 innings per 10 points, then stuff
#   (-0.44), stamina (-0.18) and ground balls (-0.15). The older SP role
#   rating leans on stamina and recovery, which barely move runs.
# - Defense: what counts is the glove at the position played, mostly the
#   outfield corners, center, catcher and the team's arms; second base and
#   first base matter least.
# - Hitting: contact and power about equally, eye and speed a little.
# Run differential and these ratings predict the rest of a season about
# equally well after RESULTS_HALF games, so that's where the blend is
# half and half.

from __future__ import annotations

from statistics import mean, pstdev

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.player.player_evaluator import LEFT_HAND_CAPPED_POSITIONS
from src.player.player_record import PlayerRecord
from src.team.lineup_optimizer import DEFENSE_IMPORTANCE, FIELD_POSITIONS

ROTATION = 5
BULLPEN = 7

HITTING_WEIGHTS = {
    "contact": 1.0,
    "power": 0.85,
    "eye": 0.35,
    "speed": 0.3,
    "base_running": 0.2,
}
PITCHING_WEIGHTS = {
    "accuracy": 0.74,
    "strikes": 0.44,
    "stamina": 0.18,
    "ground_balls": 0.15,
}
RELIEF_WEIGHTS = {k: w for k, w in PITCHING_WEIGHTS.items() if k != "stamina"}
ROTATION_SHARE = 0.65  # of the pitching score; the bullpen gets the rest

# The skill a position's glove runs on, and how much that spot's defense
# is worth (runs a season per 10 points, roughly, from the sims).
POSITION_SKILL = {
    "c": "catching",
    "1b": "infield",
    "2b": "infield",
    "3b": "infield",
    "ss": "infield",
    "lf": "outfield",
    "cf": "outfield",
    "rf": "outfield",
}
POSITION_WEIGHT = {
    "c": 1.6,
    "1b": 0.5,
    "2b": 0.6,
    "3b": 0.9,
    "ss": 1.2,
    "lf": 1.4,
    "cf": 2.2,
    "rf": 3.2,
}
ARM_SHARE = 0.3  # of the defense score: the fielders' average arm

# How much each area counts toward the team's rating (by z-score).
AREA_WEIGHTS = {"hitting": 0.25, "pitching": 0.4, "defense": 0.35}
AREAS = tuple(AREA_WEIGHTS)

# Games at which results count as much as the roster ratings.
RESULTS_HALF = 36


def _weighted(skills, weights: dict[str, float]) -> float:
    return sum(skills[k] * w for k, w in weights.items()) / sum(weights.values())


def starting_nine(
    hitters: list[tuple[PlayerRecord, dict]],
) -> list[tuple[PlayerRecord, str]]:
    """The team's likely everyday lineup with each player's position, picked
    the way the lineup optimizer does it: bat plus glove at the spot."""
    positions = FIELD_POSITIONS + ["dh"]
    if not hitters:
        return []

    def value(p: PlayerRecord, r: dict, pos: str) -> float:
        v = r.get("overall_offense", 0)
        if pos == "dh":
            return v
        v += DEFENSE_IMPORTANCE[pos] * r.get(pos, 0)
        if pos in LEFT_HAND_CAPPED_POSITIONS and (p.throws or "R").upper() == "L":
            v -= 1000
        return v

    grid = np.array([[value(p, r, pos) for pos in positions] for p, r in hitters])
    rows, cols = linear_sum_assignment(grid, maximize=True)
    return [(hitters[r][0], positions[c]) for r, c in zip(rows, cols)]


def team_strength(
    players: list[tuple[PlayerRecord, dict]], groups: dict[str, str]
) -> dict[str, float]:
    """A roster's hitting, pitching and defense scores (on the 0-100 skill
    scale), plus the rotation and bullpen that make up its pitching.
    `players` is the major league roster with each player's ratings;
    `groups` puts each pitcher in the rotation (sp) or bullpen (rp).
    The welcome screen's scouting report ranks teams on these too."""
    hitters = [(p, r) for p, r in players if not p.is_pitcher()]
    pitchers = [p for p, _ in players if p.is_pitcher()]
    nine = starting_nine(hitters)

    hitting = mean(_weighted(p.skills, HITTING_WEIGHTS) for p, _ in nine) if nine else 0
    fielders = [(p, pos) for p, pos in nine if pos != "dh"]
    if fielders:
        glove = sum(
            POSITION_WEIGHT[pos] * p.skills[POSITION_SKILL[pos]] for p, pos in fielders
        ) / sum(POSITION_WEIGHT[pos] for _, pos in fielders)
        arm = mean(p.skills["arm"] for p, _ in fielders)
        defense = (1 - ARM_SHARE) * glove + ARM_SHARE * arm
    else:
        defense = 0

    def best(group: str, weights: dict, n: int) -> float:
        scores = sorted(
            (
                _weighted(p.skills, weights)
                for p in pitchers
                if groups.get(p.id) == group
            ),
            reverse=True,
        )[:n]
        return mean(scores) if scores else 0

    rotation = best("sp", PITCHING_WEIGHTS, ROTATION)
    bullpen = best("rp", RELIEF_WEIGHTS, BULLPEN)
    pitching = ROTATION_SHARE * rotation + (1 - ROTATION_SHARE) * bullpen
    return {
        "hitting": hitting,
        "pitching": pitching,
        "defense": defense,
        "rotation": rotation,
        "bullpen": bullpen,
    }


def zscores(values: dict[str, float]) -> dict[str, float]:
    """Each team's distance from the league average, in standard deviations."""
    if not values:
        return {}
    avg = mean(values.values())
    sd = pstdev(values.values())
    return {k: (v - avg) / sd if sd else 0.0 for k, v in values.items()}


def results_weight(games: float) -> float:
    """How much results count against the roster ratings after `games`."""
    return games / (games + RESULTS_HALF) if games > 0 else 0.0


def roster_rating(strength: dict[str, dict[str, float]]) -> dict[str, float]:
    """Each team's overall rating on paper, as a z-score: its hitting,
    pitching and defense z-scores weighted by AREA_WEIGHTS."""
    teams = list(strength)
    area_z = {a: zscores({t: strength[t][a] for t in teams}) for a in AREAS}
    return zscores(
        {t: sum(AREA_WEIGHTS[a] * area_z[a][t] for a in AREAS) for t in teams}
    )


def power_scores(
    strength: dict[str, dict[str, float]], records: dict[str, dict]
) -> dict[str, dict[str, float]]:
    """Blend roster strength with results for every team.

    strength: {team_id: team_strength(...)}
    records: {team_id: {"g", "rs", "ra"}} games played and runs so far.
    Returns {team_id: {"power", "hitting", "pitching", "defense"}}, each a
    z-score (higher is better). Hitting folds in runs scored and pitching
    runs allowed; defense is ratings only."""
    teams = list(strength)
    area_z = {a: zscores({t: strength[t][a] for t in teams}) for a in AREAS}
    rating = roster_rating(strength)

    games = {t: records.get(t, {}).get("g", 0) for t in teams}
    played = [t for t in teams if games[t]]

    def per_game(key: str) -> dict[str, float]:
        return {t: records[t][key] / games[t] for t in played}

    rs = zscores(per_game("rs"))
    ra = {t: -z for t, z in zscores(per_game("ra")).items()}
    rd = zscores({t: (records[t]["rs"] - records[t]["ra"]) / games[t] for t in played})

    out = {}
    for t in teams:
        w = results_weight(games[t])
        out[t] = {
            "power": (1 - w) * rating[t] + w * rd.get(t, 0.0),
            "hitting": (1 - w) * area_z["hitting"][t] + w * rs.get(t, 0.0),
            "pitching": (1 - w) * area_z["pitching"][t] + w * ra.get(t, 0.0),
            "defense": area_z["defense"][t],
        }
    return out
