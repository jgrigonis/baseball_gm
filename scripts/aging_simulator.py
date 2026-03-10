# scripts/aging_simulator.py
"""
Baseball Player Skill Aging Simulator
======================================
All aging-curve constants live at the top of this file.
Tweak any value, then run scenarios from __main__.

Usage:
    python aging_simulator.py
"""

import random
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════
#  AGING CURVE CONSTANTS
#  Each group corresponds to one delta function.
#  PHASE_BREAKS are exclusive upper bounds: the phase fires when
#  age < break.  The last rate/noise applies for all remaining ages.
# ═══════════════════════════════════════════════════════════════

# ── Speed (SP) — physical, peaks 22-26, sharp fall after 30 ──
SP_PHASE_BREAKS = [22, 27, 31, 34]  # age < break → use that phase
SP_RATES = [1.2, 0.1, -0.9, -2.2, -2.8]
SP_NOISES = [0.5, 0.4, 0.5, 0.6, 0.7]

# ── Power (PO) — physical, slow rise then long plateau ──
PO_PHASE_BREAKS = [21, 29, 33]
PO_RATES = [2.0, 0.7, -0.2, -1.6]
PO_NOISES = [0.7, 0.5, 0.5, 0.7]

# ── Arm (AR) — physical, peaks mid-20s, declines from 30 ──
AR_PHASE_BREAKS = [24, 29, 33]
AR_RATES = [1.6, 0.2, -1.0, -1.8]
AR_NOISES = [0.5, 0.4, 0.5, 0.6]

# ── Strikes / K (KK) — raw talent, can't be coached ──
KK_PHASE_BREAKS = [24, 28, 32]
KK_RATES = [1.8, 0.4, -0.6, -2.0]
KK_NOISES = [0.6, 0.5, 0.5, 0.7]

# ── Clutch (CL) — cognitive random walk, vet upward drift ──
CL_VET_AGE = 28  # age at which vet bonus kicks in
CL_VET_BONUS = 0.35  # annual bonus once veteran
CL_NOISE = 1.6  # wide noise; clutch is hard to predict

# ── Eye / plate discipline (EY) — coaching-sensitive growth ──
EY_PHASE_BREAKS = [27, 33, 36]
EY_RATES = [1.3, 0.4, -0.4, -1.1]
EY_NOISES = [0.5, 0.4, 0.4, 0.5]
EY_COACHED = [True, True, False, False]  # coaching multiplier applied?

# ── Contact (CT) — trainable; very slow decline after mid-30s ──
CT_PHASE_BREAKS = [27, 34, 37]
CT_RATES = [1.2, 0.5, -0.3, -0.9]
CT_NOISES = [0.5, 0.4, 0.4, 0.4]
CT_COACHED = [True, True, False, False]

# ── Base Running (BR) — decision-making, never declines ──
BR_PHASE_BREAKS = [34]
BR_RATES = [0.9, 0.1]
BR_NOISES = [0.4, 0.3]
BR_COACHED = [True, True]  # coaching always applied

# ── Technical skills (BU, CA, IF, OF, GB) — always upward ──
TECH_BASE_RATE = 0.8
TECH_NOISE = 0.4
TECH_SLOW_AFTER = 33  # age after which growth slows
TECH_SLOW_MULT = 0.45  # multiplier applied after slowdown age

# ── Pitching Accuracy (AC) — asymptotes toward player ceiling ──
AC_BASE_RATE = 0.55
AC_NOISE = 0.3
AC_CEILING = 90  # hard ceiling; growth slows as val approaches this
AC_DIST_DIVISOR = 45.0  # normalises distance-to-ceiling

# ── Pitching Stamina (ST) — rises early, declines from 30+ ──
ST_PHASE_BREAKS = [26, 31, 34]
ST_RATES = [1.1, 0.3, -1.0, -2.0]
ST_NOISES = [0.5, 0.4, 0.5, 0.7]
ST_COACHED = [True, True, False, False]

# ── Pitching Recovery (RE) — most coaching-sensitive ──
RE_PHASE_BREAKS = [26, 31, 34]
RE_RATES = [1.3, 0.5, -0.8, -1.7]
RE_NOISES = [0.5, 0.4, 0.5, 0.7]
RE_COACHED = [True, True, False, False]


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


def noise(rng: random.Random, scale: float = 1.0) -> float:
    return rng.gauss(0, scale)


def clamp(val, lo: int = 1, hi: int = 100) -> float:
    return max(lo, min(hi, int(round(val))))


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
#  DELTA FUNCTIONS
# ═══════════════════════════════════════════════════════════════


def delta_SP(age: int, val: float, rng: random.Random) -> float:
    return phased_delta(age, rng, SP_PHASE_BREAKS, SP_RATES, SP_NOISES)


def delta_PO(age: int, val: float, rng: random.Random) -> float:
    return phased_delta(age, rng, PO_PHASE_BREAKS, PO_RATES, PO_NOISES)


def delta_AR(age: int, val: float, rng: random.Random) -> float:
    return phased_delta(age, rng, AR_PHASE_BREAKS, AR_RATES, AR_NOISES)


def delta_KK(age: int, val: float, rng: random.Random) -> float:
    return phased_delta(age, rng, KK_PHASE_BREAKS, KK_RATES, KK_NOISES)


def delta_CL(
    age: int, val: float, rng: random.Random, playoff_boost: float = 0.0
) -> float:
    vet_bonus = CL_VET_BONUS if age >= CL_VET_AGE else 0.0
    return vet_bonus + playoff_boost + noise(rng, CL_NOISE)


def delta_EY(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    return phased_delta(
        age, rng, EY_PHASE_BREAKS, EY_RATES, EY_NOISES, EY_COACHED, coaching
    )


def delta_CT(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    return phased_delta(
        age, rng, CT_PHASE_BREAKS, CT_RATES, CT_NOISES, CT_COACHED, coaching
    )


def delta_BR(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    return phased_delta(
        age, rng, BR_PHASE_BREAKS, BR_RATES, BR_NOISES, BR_COACHED, coaching
    )


def delta_technical_up(
    age: int, val: float, rng: random.Random, coaching: float = 1.0
) -> float:
    rate = coaching * (TECH_BASE_RATE + noise(rng, TECH_NOISE))
    if age > TECH_SLOW_AFTER:
        rate *= TECH_SLOW_MULT
    return max(0.0, rate)


def delta_AC(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    distance = max(0.0, AC_CEILING - val)
    base = (
        coaching * (AC_BASE_RATE + noise(rng, AC_NOISE)) * (distance / AC_DIST_DIVISOR)
    )
    return max(0.0, base)


def delta_ST(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    return phased_delta(
        age, rng, ST_PHASE_BREAKS, ST_RATES, ST_NOISES, ST_COACHED, coaching
    )


def delta_RE(age: int, val: float, rng: random.Random, coaching: float = 1.0) -> float:
    return phased_delta(
        age, rng, RE_PHASE_BREAKS, RE_RATES, RE_NOISES, RE_COACHED, coaching
    )


# ═══════════════════════════════════════════════════════════════
#  SIMULATION CORE
# ═══════════════════════════════════════════════════════════════

ALL_SKILLS = [
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

DEFAULT_INITIAL_SKILLS: dict[str, int] = {skill: 50 for skill in ALL_SKILLS}


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

    for age in range(start_age, end_age):
        s["speed"] += delta_SP(age, s["speed"], rng)
        s["power"] += delta_PO(age, s["power"], rng)
        s["arm"] += delta_AR(age, s["arm"], rng)
        s["strikes"] += delta_KK(age, s["strikes"], rng)
        s["clutch"] += delta_CL(age, s["clutch"], rng)
        s["eye"] += delta_EY(age, s["eye"], rng, coaching)
        s["contact"] += delta_CT(age, s["contact"], rng, coaching)
        s["base_running"] += delta_BR(age, s["base_running"], rng, coaching)
        s["bunting"] += delta_technical_up(age, s["bunting"], rng, coaching)
        s["catching"] += delta_technical_up(age, s["catching"], rng, coaching)
        s["infield"] += delta_technical_up(age, s["infield"], rng, coaching)
        s["outfield"] += delta_technical_up(age, s["outfield"], rng, coaching)
        s["ground_balls"] += delta_technical_up(age, s["ground_balls"], rng, coaching)
        s["accuracy"] += delta_AC(age, s["accuracy"], rng, coaching)
        s["stamina"] += delta_ST(age, s["stamina"], rng, coaching)
        s["recovery"] += delta_RE(age, s["recovery"], rng, coaching)

        for k in s:
            s[k] = float(clamp(s[k]))

        records.append({"age": age + 1, **{k: int(round(v)) for k, v in s.items()}})

    return records


@dataclass
class Scenario:
    name: str
    initial_skills: dict = field(default_factory=lambda: dict(DEFAULT_INITIAL_SKILLS))
    start_age: int = 17
    end_age: int = 40
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

TARGET_AGES = [20, 25, 30, 35]


def print_scenario(scenario: Scenario, results: dict) -> None:
    print(f"\n{'═' * 72}")
    print(f"  {scenario.name}")
    print(
        f"  coaching={scenario.coaching}  N={scenario.n_sims}  "
        f"ages {scenario.start_age}–{scenario.end_age - 1}"
    )
    print(f"{'═' * 72}")

    header = f"  {'Skill':<15}" + "".join(
        f"  {'Age ' + str(a):>14}" for a in TARGET_AGES
    )
    print(header)
    print(f"  {'-' * 14}" + "  " + "  ".join(["-" * 14] * len(TARGET_AGES)))

    for skill in ALL_SKILLS:
        by_age = {r["age"]: r for r in results[skill]}
        row = f"  {skill:<15}"
        for age in TARGET_AGES:
            if age in by_age:
                r = by_age[age]
                row += f"  {r['p50']:3d} [{r['p10']:3d}–{r['p90']:3d}]"
            else:
                row += f"  {'N/A':>14}"
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
        Scenario(
            "Elite coaching environment (coaching 1.3)",
            coaching=1.3,
        ),
        Scenario(
            "Poor development (coaching 0.7)",
            coaching=0.7,
        ),
        Scenario(
            "Five-tool prospect — high speed & arm",
            initial_skills={
                **DEFAULT_INITIAL_SKILLS,
                "speed": 75,
                "arm": 72,
                "outfield": 68,
            },
            coaching=1.0,
        ),
        Scenario(
            "Power hitter — high PO, low speed",
            initial_skills={
                **DEFAULT_INITIAL_SKILLS,
                "power": 78,
                "contact": 62,
                "speed": 35,
            },
            coaching=1.0,
        ),
        Scenario(
            "Late bloomer — starts age 20",
            initial_skills={**DEFAULT_INITIAL_SKILLS, "power": 45, "contact": 45},
            start_age=20,
            coaching=1.2,
        ),
    ]

    for sc in scenarios:
        results = run_scenario(sc)
        print_scenario(sc, results)

    print()
