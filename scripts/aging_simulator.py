# scripts/aging_simulator.py
"""
Baseball Player Skill Aging Simulator
======================================
There are no caps currently here.

It uses the official SkillAging class

Usage:
    python aging_simulator.py
"""

import random
from dataclasses import dataclass, field

from src.player.player_skill_aging import SkillAging, noise
from src.util.clamp import clamp

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


# def noise(rng: random.Random, scale: float = 1.0) -> float:
#     return rng.gauss(0, scale)


# def clamp(val, lo: int = 1, hi: int = 100) -> float:
#     return max(lo, min(hi, int(round(val))))


def phased_delta(
    age: int,
    rng: random.Random,
    breaks: list[int],
    rates: list[float],
    noises: list[float],
    coached: list[bool] | None = None,
    coaching: float = 1.0,
) -> float:
    """
    Find the phase for *age* and return rate + noise, optionally scaled
    by the coaching multiplier (only when coached[phase] is True).
    """
    idx = len(breaks)  # default → last phase
    for i, b in enumerate(breaks):
        if age < b:
            idx = i
            break

    raw = rates[idx] + noise(rng, noises[idx])
    if coached and coached[idx]:
        return coaching * raw
    return raw


# ═══════════════════════════════════════════════════════════════
#  SIMULATION CORE
# ═══════════════════════════════════════════════════════════════

ALL_SKILLS = [
    "durability",
    "clutch",
    "speed",
    "power",
    "eye",
    "contact",
    "base_running",
    "bunting",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "stamina",
    "recovery",
    "ground_balls",
    "strikes",
]

DEFAULT_10_SKILLS: dict[str, int] = {skill: 10 for skill in ALL_SKILLS}
DEFAULT_20_SKILLS: dict[str, int] = {skill: 20 for skill in ALL_SKILLS}
DEFAULT_30_SKILLS: dict[str, int] = {skill: 30 for skill in ALL_SKILLS}
DEFAULT_40_SKILLS: dict[str, int] = {skill: 40 for skill in ALL_SKILLS}
DEFAULT_50_SKILLS: dict[str, int] = {skill: 50 for skill in ALL_SKILLS}
DEFAULT_60_SKILLS: dict[str, int] = {skill: 60 for skill in ALL_SKILLS}
DEFAULT_70_SKILLS: dict[str, int] = {skill: 70 for skill in ALL_SKILLS}
DEFAULT_80_SKILLS: dict[str, int] = {skill: 80 for skill in ALL_SKILLS}
DEFAULT_90_SKILLS: dict[str, int] = {skill: 90 for skill in ALL_SKILLS}

FULL_WIDTH = 92
HEADER_WIDTH = 14
AGE_WIDTH = 13


def simulate_one(
    initial_skills: dict[str, int | float],
    start_age: int,
    end_age: int,
    coaching: float,
    rng: random.Random,
) -> list[dict]:
    """Simulate one career from start_age to end_age (exclusive)."""
    s = {k: float(v) for k, v in initial_skills.items()}
    records = [{"age": start_age, **{k: int(round(v)) for k, v in s.items()}}]

    SA = SkillAging()

    for age in range(start_age, end_age):
        s["speed"] += SA.delta_SP(age, s["speed"], rng)
        s["power"] += SA.delta_PO(age, s["power"], rng)
        s["arm"] += SA.delta_AR(age, s["arm"], rng)
        s["strikes"] += SA.delta_KK(age, s["strikes"], rng)
        s["clutch"] += SA.delta_CL(age, s["clutch"], rng)
        s["eye"] += SA.delta_EY(age, s["eye"], rng, coaching)
        s["contact"] += SA.delta_CT(age, s["contact"], rng, coaching)
        s["base_running"] += SA.delta_BR(age, s["base_running"], rng, coaching)
        s["bunting"] += SA.delta_BU(age, s["bunting"], rng, coaching)
        s["catching"] += SA.delta_CA(age, s["catching"], rng, coaching)
        s["infield"] += SA.delta_IF(age, s["infield"], rng, coaching)
        s["outfield"] += SA.delta_OF(age, s["outfield"], rng, coaching)
        s["ground_balls"] += SA.delta_GB(age, s["ground_balls"], rng, coaching)
        s["accuracy"] += SA.delta_AC(age, s["accuracy"], rng, coaching)
        s["stamina"] += SA.delta_ST(age, s["stamina"], rng, coaching)
        s["recovery"] += SA.delta_RE(age, s["recovery"], rng, coaching)
        s["durability"] += SA.delta_DU(age, s["durability"], rng, coaching)

        for k in s:
            s[k] = float(clamp(s[k], 1, 100, precision=4))

        records.append({"age": age + 1, **{k: int(round(v)) for k, v in s.items()}})

    return records


@dataclass
class Scenario:
    name: str
    initial_skills: dict = field(default_factory=lambda: dict(DEFAULT_50_SKILLS))
    start_age: int = 17
    end_age: int = 41
    coaching: float = 1.0
    n_sims: int = 500
    seed: int = 42


def run_scenario(scenario: Scenario) -> dict[str, list[dict]]:
    """
    Run N simulations.  Returns a dict of skill → list of {age, p10, p50, p90}.
    """
    rng = random.Random(scenario.seed)
    all_sims: list[list[dict]] = [
        simulate_one(
            scenario.initial_skills,
            scenario.start_age,
            scenario.end_age,
            scenario.coaching,
            rng,
        )
        for _ in range(scenario.n_sims)
    ]

    ages = [r["age"] for r in all_sims[0]]
    results: dict[str, list[dict]] = {}

    for skill in ALL_SKILLS:
        skill_rows = []
        for i, age in enumerate(ages):
            vals = sorted(sim[i][skill] for sim in all_sims)
            n = len(vals)
            skill_rows.append(
                {
                    "age": age,
                    "p10": vals[max(0, int(n * 0.10))],
                    "p50": vals[max(0, int(n * 0.50))],
                    "p90": vals[min(n - 1, int(n * 0.90))],
                }
            )
        results[skill] = skill_rows

    return results


# ═══════════════════════════════════════════════════════════════
#  REPORTING
# ═══════════════════════════════════════════════════════════════

TARGET_AGES = [20, 25, 30, 35, 40]


def print_scenario(scenario: Scenario, results: dict) -> None:
    print(f"\n{'═' * FULL_WIDTH}")
    print(f"  {scenario.name}")
    print(f"  N={scenario.n_sims}  ages {scenario.start_age}-{scenario.end_age - 1}")
    print(f"{'═' * FULL_WIDTH}")

    header = f"  {'Skill':<{HEADER_WIDTH}}" + "".join(
        f"  {'Age ' + str(a):>{AGE_WIDTH}}" for a in TARGET_AGES
    )
    print(header)
    print(
        f"  {'-' * HEADER_WIDTH}"
        + "   "
        + "  ".join(["-" * AGE_WIDTH] * len(TARGET_AGES))
    )

    for skill in ALL_SKILLS:
        by_age = {r["age"]: r for r in results[skill]}
        row = f"  {skill:<{HEADER_WIDTH}}"
        for age in TARGET_AGES:
            if age in by_age:
                r = by_age[age]
                row += f"  {r['p50']:3d} [{r['p10']:3d}-{r['p90']:3d}]"
            else:
                row += f"  {'N/A':>{AGE_WIDTH}}"
        print(row)


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT — define your scenarios here
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    scenarios = [
        Scenario(
            "Baseline — average starter (coaching 1.0)",
            coaching=1.0,
        ),
        # We don't really do coaching differences yet
        # Scenario(
        #     "Elite coaching environment (coaching 1.3)",
        #     coaching=1.3,
        # ),
        # Scenario(
        #     "Poor development (coaching 0.7)",
        #     coaching=0.7,
        # ),
        Scenario(
            "70 skill player",
            initial_skills={
                **DEFAULT_70_SKILLS,
            },
            coaching=1.0,
        ),
        Scenario(
            "90 skill player",
            initial_skills={
                **DEFAULT_90_SKILLS,
            },
            coaching=1.0,
        ),
        Scenario(
            "Late bloomer — starts age 20 - 40 skills",
            initial_skills={**DEFAULT_40_SKILLS},
            start_age=20,
            coaching=1.0,
        ),
    ]

    for sc in scenarios:
        results = run_scenario(sc)
        print_scenario(sc, results)

    print()
