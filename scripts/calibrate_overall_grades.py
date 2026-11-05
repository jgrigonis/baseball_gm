"""
Calibrate the curved overall-grade cutoffs in src/api/grade_curves.py.

An overall rating is an average of many skills, so it spreads far less than a
single skill and the plain 5-points-per-grade scale crowds almost everyone
into B to C. Instead, each kind of overall is graded on a curve: this script
simulates the population that kind is shown for, and finds the score at
which each grade starts so the population lands on TARGET_SHARES.

    prospect  draft classes, built the way DraftGenerator builds them
    hitter    position players on freshly generated 26-man rosters
    pitcher   SP/RP on the same rosters, rated max(sp, rp)
    team_*    those rosters' areas on the welcome scouting report
              (welcome.area_scores: lineup, rotation, bullpen, defense,
              power, speed)
    roles     the role and position ratings on the same rosters, each
              graded against the players who fill that role: SP against
              starters, RP and CP against relievers, SS against shortstops,
              IF/OF against the infielders/outfielders, and the hitter roles
              and best defense against every position player. These go in
              ROLE_CUTOFFS.

Usage:
    uv run python -m scripts.calibrate_overall_grades [--classes 80] [--teams 1200]

Paste the printed tables into src/api/grade_curves.py.
"""

import argparse
import collections
import random

from src.api.grade_curves import GRADES
from src.api.view_models.welcome import area_scores
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.draft_strategy import ratings
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_factory import PlayerFactory
from src.team.team_factory import TeamFactory

# Share of the population at each grade, best to worst (percent). A+ is rare
# enough that a 650-player draft class sees one about every other year.
TARGET_SHARES = {
    "prospect": [0.1, 0.7, 2.2, 5, 9, 13, 16, 17, 14, 10, 6.5, 3.5, 3],
    "hitter": [0.3, 1.2, 3, 6, 10, 14, 16, 16, 13, 9, 6, 3.5, 2],
    "pitcher": [0.3, 1.2, 3, 6, 10, 14, 16, 16, 13, 9, 6, 3.5, 2],
}
# A league has 20 to 30 teams, so team grades use a flatter curve: most
# leagues have a team or two at each end.
TEAM_SHARES = [2, 4, 6, 8, 10, 11, 12, 12, 11, 9, 7, 5, 3]
TEAM_AREAS = ("lineup", "rotation", "bullpen", "defense", "power", "speed")
TARGET_SHARES.update({f"team_{area}": TEAM_SHARES for area in TEAM_AREAS})

# Role ratings and who each is graded against (roster positions).
INFIELD = ("2b", "3b", "ss", "if")
OUTFIELD = ("lf", "cf", "rf", "of")
HITTERS = ("c", "1b") + INFIELD + OUTFIELD
ROLE_POOLS = {
    "sp": ("sp",),
    "rp": ("rp",),
    "cp": ("rp",),
    "lead_off": HITTERS,
    "contact_hitter": HITTERS,
    "power_hitter": HITTERS,
    "overall_offense": HITTERS,
    "best_def": HITTERS,
    "c": ("c",),
    "1b": ("1b",),
    "2b": ("2b",),
    "3b": ("3b",),
    "ss": ("ss",),
    "lf": ("lf",),
    "cf": ("cf",),
    "rf": ("rf",),
    "if": INFIELD,
    "of": OUTFIELD,
}
ROLE_SHARES = TARGET_SHARES["hitter"]


def prospect_scores(n_classes: int, rng: random.Random) -> list[int]:
    gen = DraftGenerator.__new__(DraftGenerator)  # no DB needed to generate
    gen.rng = rng
    gen.factory = PlayerFactory(rng=rng)
    scores = []
    for _ in range(n_classes):
        for p in gen._generate_prospects():
            scores.append(PlayerEvaluator.rate_player(p.skills, p.throws)["prospect"])
    return scores


def roster_scores(n_teams: int, rng: random.Random) -> dict[str, list[float]]:
    factory = TeamFactory(rng=rng)
    out = {"hitter": [], "pitcher": []}
    out.update({f"team_{area}": [] for area in TEAM_AREAS})
    out.update({f"role_{role}": [] for role in ROLE_POOLS})
    for i in range(n_teams):
        team = factory.generate_team(city=f"City{i}", mascot="Sims", size=26)
        rated = [(p, ratings(p)) for p in team.players]
        for p, r in rated:
            if p.position in ("sp", "rp"):
                out["pitcher"].append(max(r["sp"], r["rp"]))
            else:
                out["hitter"].append(r["overall_player"])
            best_def = max(r["if"], r["of"], r["c"], r["1b"])
            for role, pool in ROLE_POOLS.items():
                if p.position in pool:
                    value = best_def if role == "best_def" else r[role]
                    out[f"role_{role}"].append(value)
        for area, value in area_scores(rated).items():
            out[f"team_{area}"].append(round(value, 1))
    return out


def cutoffs(scores: list[float], shares: list[float]) -> list[float]:
    """The lowest score for each grade A+ .. D- (F takes the rest)."""
    n = len(scores)
    counts = collections.Counter()
    for s in scores:
        counts[s] += 1
    levels = sorted(counts, reverse=True)
    share_at = {}  # share of players scoring >= each level
    running = 0
    for level in levels:
        running += counts[level]
        share_at[level] = 100 * running / n

    result, cumulative = [], 0.0
    for share in shares[:-1]:
        cumulative += share
        # Scores are integers, so shares move in steps: take the cut that
        # lands closest to the target, always below the previous grade's.
        options = [lv for lv in levels if not result or lv < result[-1]]
        cut = min(options, key=lambda lv: abs(share_at[lv] - cumulative))
        result.append(cut)
    return result


def distribution(scores: list[float], cuts: list[float]) -> list[float]:
    counts = collections.Counter(sum(1 for c in cuts if s < c) for s in scores)
    return [100 * counts[i] / len(scores) for i in range(len(GRADES))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", type=int, default=80)
    ap.add_argument("--teams", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=20261102)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    pops = {"prospect": prospect_scores(args.classes, rng)}
    pops.update(roster_scores(args.teams, rng))

    for kind, scores in pops.items():
        shares = ROLE_SHARES if kind.startswith("role_") else TARGET_SHARES[kind]
        cuts = cutoffs(scores, shares)
        dist = distribution(scores, cuts)
        print(f"# {kind}: {len(scores)} samples")
        print(f'    "{kind.removeprefix("role_")}": {cuts},')
        print("    # " + "  ".join(f"{g} {d:.1f}%" for g, d in zip(GRADES, dist)))


if __name__ == "__main__":
    main()
