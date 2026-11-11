"""
How a league's big league talent moves over the seasons, without playing
games. Use it to retune the draft class settings in
src/league/offseason/draft_generator.py (DRAFT_SPREAD, DRAFT_OFFSET,
DRAFT_SKILL_OFFSETS): a mature league should sit where year one does.

Each season: every player ages (PlayerSkills.age_to), players retire
(retirement_chance, roughly), a draft class is generated the way
DraftGenerator makes one, teams snake-draft 20 rounds by prospect rating,
orgs are trimmed to 160, and each team picks its 26-man (big_26). Nobody
plays and retirement is rough, so treat the numbers as a guide and confirm
in a real league.

Prints, each season, the 26-man average role rating (hitters, pitchers),
age, the share of 26-man players the league drafted, and each Scouting
Report area's league mean and spread. At the end it prints how far each
skill moved from year one: a skill that climbs needs a bigger offset.

Usage:
    uv run python -m scripts.talent_drift_sim [--teams 30] [--years 20] [--seed 11] [--old]
"""

import argparse
import dataclasses
import random
import statistics

from src.api.view_models.welcome import area_scores
from src.league.offseason import draft_generator
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.draft_strategy import ratings
from src.league.offseason.retirement import RetirementFactors, retirement_chance
from src.league.offseason.snake_draft import ROUNDS
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_factory import PlayerFactory
from src.team.team_factory import TeamFactory

ORG_LIMIT = 160
AREAS = ("lineup", "rotation", "bullpen", "defense", "power", "speed")


def is_pitcher(p) -> bool:
    return p.position in ("sp", "rp")


def role(p, r) -> float:
    return max(r["sp"], r["rp"]) if is_pitcher(p) else r["overall_player"]


def prospect(p) -> float:
    return PlayerEvaluator.rate_player(p.skills, p.throws)["prospect"]


# The 26-man: the best player at each position (two catchers), five
# starters and eight relievers by their role ratings, then the best four
# position players left.
FIELD = ("c", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf")


def big_26(org: list) -> list:
    rated = [(p, ratings(p)) for p in org]
    picked, used = [], set()

    def take(pool, key, n):
        for p, r in sorted(pool, key=key, reverse=True):
            if n == 0:
                break
            if p.id not in used:
                used.add(p.id)
                picked.append((p, r))
                n -= 1

    pitchers = [x for x in rated if is_pitcher(x[0])]
    take([x for x in pitchers if x[0].position == "sp"], lambda x: x[1]["sp"], 5)
    take(pitchers, lambda x: x[1]["rp"], 8)
    hitters = [x for x in rated if not is_pitcher(x[0])]
    for pos in FIELD:
        take(
            hitters,
            lambda x, pos=pos: x[1]["overall_offense"] + x[1][pos],
            1,
        )
    take(hitters, lambda x: x[1]["overall_player"], 4)
    return picked


def skill_means(rosters: list) -> dict[str, dict[str, float]]:
    out = {}
    for group, test in (
        ("hitter", lambda p: not is_pitcher(p)),
        ("pitcher", is_pitcher),
    ):
        players = [p for t in rosters for p, _ in t if test(p)]
        out[group] = {
            k: statistics.mean(p.skills.as_dict()[k] for p in players)
            for k in players[0].skills.as_dict()
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, default=30)
    ap.add_argument(
        "--swings", action="store_true", help="breakout/crashout winters"
    )
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument(
        "--old",
        action="store_true",
        help="draft classes generated like opening-day players (no offsets)",
    )
    args = ap.parse_args()
    if args.old:
        draft_generator.DRAFT_SPREAD = 1.0
        draft_generator.DRAFT_OFFSET = 0.0
        draft_generator.DRAFT_SKILL_OFFSETS = {"hitter": {}, "pitcher": {}}

    rng = random.Random(args.seed)
    factory = TeamFactory(rng=rng)
    orgs = [
        list(factory.generate_team(city=f"C{i}", mascot="M", size=26).players)
        for i in range(args.teams)
    ]
    founders = {p.id for org in orgs for p in org}
    gen = DraftGenerator.__new__(DraftGenerator)  # no DB needed to generate
    gen.rng = rng
    gen.factory = PlayerFactory(rng=rng)

    first = None
    for year in range(args.years + 1):
        rosters = [big_26(org) for org in orgs]
        on_26 = [(p, r) for t in rosters for p, r in t]
        hit = [role(p, r) for p, r in on_26 if not is_pitcher(p)]
        pit = [role(p, r) for p, r in on_26 if is_pitcher(p)]
        drafted = sum(p.id not in founders for p, _ in on_26) / len(on_26)
        line = (
            f"yr {year:2d}  hit {statistics.mean(hit):5.1f}  pit {statistics.mean(pit):5.1f}"
            f"  age {statistics.mean(p.age for p, _ in on_26):4.1f}  drafted {drafted:4.0%} |"
        )
        areas = [area_scores(t) for t in rosters]
        for k in AREAS:
            v = [a[k] for a in areas]
            line += f"  {k} {statistics.mean(v):5.1f}±{statistics.pstdev(v):3.1f}"
        print(line, flush=True)
        if first is None:
            first = skill_means(rosters)
        if year == args.years:
            break

        # Age and retire.
        ids_26 = {p.id for p, _ in on_26}
        median = {
            True: statistics.median(pit),
            False: statistics.median(hit),
        }
        for i, org in enumerate(orgs):
            kept = []
            for p in org:
                rating = role(p, ratings(p))
                on = p.id in ids_26
                chance = retirement_chance(
                    p.age,
                    RetirementFactors(
                        playing_time=0.7 if on else 0.0,
                        below_median=median[is_pitcher(p)] - rating,
                    ),
                )
                # Org filler who'll never make it washes out.
                if not on and p.age >= 24 and rating < median[is_pitcher(p)] - 15:
                    chance = max(chance, min(0.95, (p.age - 23) * 0.2))
                if rng.random() < chance:
                    continue
                skills = p.skills.age_to(
                    p.age + 1,
                    from_age=p.age,
                    rng=rng,
                    caps=p.caps,
                    coaching=0.93 if on else 1.0,
                    swings=args.swings,
                )
                kept.append(dataclasses.replace(p, skills=skills))
            orgs[i] = kept

        # Draft, then trim each org to its 26-man plus its best prospects.
        pool = sorted(gen._generate_prospects(), key=prospect, reverse=True)
        order = list(range(args.teams))
        rng.shuffle(order)
        for rnd in range(ROUNDS):
            for t in order if rnd % 2 == 0 else order[::-1]:
                if pool:
                    orgs[t].append(pool.pop(0))
        for i, org in enumerate(orgs):
            if len(org) > ORG_LIMIT:
                keep = {p.id for p, _ in big_26(org)}
                rest = sorted(
                    (p for p in org if p.id not in keep), key=prospect, reverse=True
                )
                orgs[i] = [p for p in org if p.id in keep] + rest[: ORG_LIMIT - 26]

    last = skill_means(rosters)
    print("\nSkill drift on 26-man rosters since year one (skills above 25 only):")
    for group in first:
        moved = [
            f"{k} {last[group][k] - first[group][k]:+.1f}"
            for k in first[group]
            if first[group][k] > 25
        ]
        print(f"  {group}: " + "  ".join(moved))


if __name__ == "__main__":
    main()
