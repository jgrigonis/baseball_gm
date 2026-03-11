# scripts/player_aging.py
# This is intended to visualize the deltas in player_skill_aging.py

"""
MLB Player Skill Aging Simulation
Tracks a single player from age 17 to 37 across 20 seasons.
All skills start at 50. Aging curves are derived from real MLB
development patterns per skill category.
"""

import random
import csv
import io


from src.player.player_skill_aging import SkillAging

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────


def clamp(val, lo=1, hi=100):
    return max(lo, min(hi, int(round(val))))


def noise(scale=1.0):
    return random.gauss(0, scale)


"""
random.gauss(0, scale) draws a single random number from a
normal (bell curve) distribution centered at 0 with a standard 
deviation of scale. In plain terms:

It returns a small positive or negative float, most of the 
time close to zero
The bigger scale is, the wider the spread of possible values
With scale=1.0, about 68% of calls return something between 
-1.0 and +1.0, and about 95% land between -2.0 and +2.0

So when you write something like return 1.2 + noise(0.5), 
you're saying "grow by roughly 1.2 this year, but add a 
realistic random wobble so no two careers are identical." 
Without it, every player aged identically.

"""

# ─────────────────────────────────────────────
#  MAIN SIMULATION
# ─────────────────────────────────────────────


def age_player_career(
    name="TEST PLAYER",
    start_age=17,
    seasons=20,
    start_skill=50,
    coaching=1.0,  # 0.8 poor | 1.0 avg | 1.2 elite
    position="sp",
    throws="R",
    bats="R",
    player_id="player_001",
    seed=None,
):

    rng = random.Random(seed)

    s = {
        k: float(start_skill)
        for k in [
            "CL",
            "SP",
            "PO",
            "EY",
            "CT",
            "BR",
            "BU",
            "CA",
            "IF",
            "OF",
            "AR",
            "AC",
            "ST",
            "RE",
            "GB",
            "KK",
        ]
    }

    rows = []

    for season_idx in range(seasons):
        age = start_age + season_idx

        # ── Snapshot BEFORE this year's aging ──────────────────────────
        row = dict(
            Name=name,
            Age=age,
            Season=season_idx + 1,
            PS=position,
            T=throws,
            B=bats,
            **{k: clamp(v) for k, v in s.items()},
            ID=player_id,
        )
        rows.append(row)

        # ── Apply one year of aging ─────────────────────────────────────
        s["SP"] += SkillAging.delta_SP(age, s["SP"], rng)
        s["PO"] += SkillAging.delta_PO(age, s["PO"], rng)
        s["AR"] += SkillAging.delta_AR(age, s["AR"], rng)
        s["KK"] += SkillAging.delta_KK(age, s["KK"], rng)
        s["CL"] += SkillAging.delta_CL(age, s["CL"], rng)
        s["EY"] += SkillAging.delta_EY(age, s["EY"], rng, coaching)
        s["CT"] += SkillAging.delta_CT(age, s["CT"], rng, coaching)
        s["BR"] += SkillAging.delta_BR(age, s["BR"], rng, coaching)
        s["BU"] += SkillAging.delta_BU(age, s["BU"], rng, coaching)
        s["CA"] += SkillAging.delta_CA(age, s["CA"], rng, coaching)
        s["IF"] += SkillAging.delta_IF(age, s["IF"], rng, coaching)
        s["OF"] += SkillAging.delta_OF(age, s["OF"], rng, coaching)
        s["GB"] += SkillAging.delta_GB(age, s["GB"], rng, coaching)
        s["AC"] += SkillAging.delta_AC(age, s["AC"], rng, coaching)
        s["ST"] += SkillAging.delta_ST(age, s["ST"], rng, coaching)
        s["RE"] += SkillAging.delta_RE(age, s["RE"], rng, coaching)

        # Clamp everything to valid range
        for k in s:
            s[k] = float(clamp(s[k]))

    return rows


# ─────────────────────────────────────────────
#  OUTPUT FORMATTERS
# ─────────────────────────────────────────────

SKILL_KEYS = [
    "CL",
    "SP",
    "PO",
    "EY",
    "CT",
    "BR",
    "BU",
    "CA",
    "IF",
    "OF",
    "AR",
    "AC",
    "ST",
    "RE",
    "GB",
    "KK",
]

CATEGORIES = {
    "PHYSICAL": ["SP", "PO", "AR", "KK"],
    "COGNITIVE": ["CL", "EY", "BR"],
    "TECHNICAL": ["CT", "BU", "CA", "IF", "OF", "AC", "ST", "RE", "GB"],
}

CATEGORY_LABELS = {
    "CL": "Clutch",
    "SP": "Speed",
    "PO": "Power",
    "EY": "Eye",
    "CT": "Contact",
    "BR": "Baserun",
    "BU": "Bunt",
    "CA": "Catch",
    "IF": "Infield",
    "OF": "Outfield",
    "AR": "Arm",
    "AC": "PitchAcc",
    "ST": "Stamina",
    "RE": "Recovery",
    "GB": "GroundBall",
    "KK": "Strikeout",
}


def sparkline(values, width=20):
    """ASCII sparkline using block chars."""
    blocks = " ▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    rng = hi - lo if hi != lo else 1
    chars = [blocks[int((v - lo) / rng * 8)] for v in values]
    return "".join(chars)


def print_career_table(rows):
    sk = SKILL_KEYS
    header = f"{'Age':>4} {'Ssn':>4} | " + "  ".join(f"{k:>4}" for k in sk)
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    for row in rows:
        vals = "  ".join(f"{row[k]:>4}" for k in sk)
        print(f"{row['Age']:>4} {row['Season']:>4} | {vals}")
    print(sep)


def print_career_arcs(rows):
    """Show per-skill sparkline + start/peak/end summary."""
    print("\n── Skill Trajectories (sparkline, age 17→37) ────────────────────────────────────────")
    print(
        f"{'Skill':<13}  {'Cat':<9}  {'Arc (17→37)':^30}  {'Start':>5}  {'Peak':>5}  {'End':>5}  {'Δ':>5}"
    )
    print("─" * 85)

    cat_map = {}
    for cat, keys in CATEGORIES.items():
        for k in keys:
            cat_map[k] = cat[:3].capitalize()

    for k in SKILL_KEYS:
        vals = [row[k] for row in rows]
        peak = max(vals)
        label = CATEGORY_LABELS[k]
        cat = cat_map.get(k, "   ")
        spark = sparkline(vals)
        delta = vals[-1] - vals[0]
        delta_str = f"{delta:+d}"
        print(
            f"{label:<13}  {cat:<9}  {spark}  {vals[0]:>5}  {peak:>5}  {vals[-1]:>5}  {delta_str:>5}"
        )


def rows_to_csv_string(rows):
    output = io.StringIO()
    fields = [
        "Name",
        "Age",
        "Season",
        "PS",
        "T",
        "B",
        "CL",
        "SP",
        "PO",
        "EY",
        "CT",
        "BR",
        "BU",
        "CA",
        "IF",
        "OF",
        "AR",
        "AC",
        "ST",
        "RE",
        "GB",
        "KK",
        "ID",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # ── Run three coaching scenarios for comparison ─────────────────────
    configs = [
        ("ELITE COACHING", 1.2, 42),
        ("AVG COACHING", 1.0, 42),
        ("POOR COACHING", 0.8, 42),
    ]

    for label, coaching_val, seed_val in configs:
        print(f"\n{'═'*72}")
        print(
            f"  {label}  (coaching={coaching_val})  —  Age 17-37, all skills start at 50"
        )
        print(f"{'═'*72}")

        career = age_player_career(
            name=f"PLAYER ({label})",
            start_age=17,
            seasons=30,
            start_skill=50,
            coaching=coaching_val,
            position="sp",
            throws="R",
            bats="R",
            player_id=f"sim_{label.lower().replace(' ','_')}",
            seed=seed_val,
        )

        print_career_table(career)
        print_career_arcs(career)

    # ── Save average-coaching CSV ────────────────────────────────────────
    avg_career = age_player_career(
        name="SIM PLAYER",
        start_age=17,
        seasons=20,
        start_skill=50,
        coaching=1.0,
        position="sp",
        throws="R",
        bats="R",
        player_id="sim_avg_001",
        seed=42,
    )

    csv_out = rows_to_csv_string(avg_career)
    path = "player_career_sim.csv"
    with open(path, "w") as f:
        f.write(csv_out)
    print(f"\nCSV saved → {path}")
