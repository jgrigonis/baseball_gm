"""
MLB Player Skill Aging Simulation
Tracks a single player from age 17 to 37 across 20 seasons.
All skills start at 50. Aging curves are derived from real MLB 
development patterns per skill category.
"""

import random
import math
import csv
import io

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
#  AGING DELTAS (one year)
#  Each function returns the raw float delta
#  to apply to a skill value.
# ─────────────────────────────────────────────

def delta_SP(age, val):
    """Run Speed — physical, peaks 22-26, sharp fall after 30."""
    if age < 22:
        return  1.2 + noise(0.5)
    elif age <= 26:
        return  0.1 + noise(0.4)
    elif age <= 30:
        return -0.9 + noise(0.5)
    elif age <= 33:
        return -2.2 + noise(0.6)
    else:
        return -2.8 + noise(0.7)

def delta_PO(age, val):
    """Batting Power — physical, slow rise > long plateau > late decline."""
    if age < 21:
        return  2.0 + noise(0.7)
    elif age <= 28:
        return  0.7 + noise(0.5)
    elif age <= 32:
        return -0.2 + noise(0.5)
    else:
        return -1.6 + noise(0.7)

def delta_AR(age, val):
    """Throwing Arm — physical, peaks mid-20s, declines from 30."""
    if age < 24:
        return  1.6 + noise(0.5)
    elif age <= 28:
        return  0.2 + noise(0.4)
    elif age <= 32:
        return -1.0 + noise(0.5)
    else:
        return -1.8 + noise(0.6)

def delta_KK(age, val):
    """Strikeout ability — physical/raw talent, can't be coached."""
    if age < 24:
        return  1.8 + noise(0.6)
    elif age <= 27:
        return  0.4 + noise(0.5)
    elif age <= 31:
        return -0.6 + noise(0.5)
    else:
        return -2.0 + noise(0.7)

def delta_CL(age, val, playoff_boost=0.0):
    """Clutch — cognitive, slight random walk, vet upward drift."""
    vet_bonus = 0.35 if age >= 28 else 0.0
    return vet_bonus + playoff_boost + noise(1.6)

def delta_EY(age, val, coaching=1.0):
    """Eye / plate discipline — peaks later than physical, gentle decline."""
    if age < 27:
        return coaching * (1.3 + noise(0.5))
    elif age <= 32:
        return coaching * (0.4 + noise(0.4))
    elif age <= 35:
        return              -0.4 + noise(0.4)
    else:
        return              -1.1 + noise(0.5)

def delta_CT(age, val, coaching=1.0):
    """Contact — trainable; very slow decline after mid-30s."""
    if age < 27:
        return coaching * (1.2 + noise(0.5))
    elif age <= 33:
        return coaching * (0.5 + noise(0.4))
    elif age <= 36:
        return              -0.3 + noise(0.4)
    else:
        return              -0.9 + noise(0.4)

def delta_BR(age, val, coaching=1.0):
    """Base running — decision-making, trends up all career, late plateau."""
    if age <= 33:
        return coaching * (0.9 + noise(0.4))
    else:
        return coaching * (0.1 + noise(0.3))   # plateau, not decline

def delta_technical_up(age, val, coaching=1.0, slow_after=33):
    """Generic always-upward technical skill (BU, CA, IF, OF, GB)."""
    rate = coaching * (0.8 + noise(0.4))
    if age > slow_after:
        rate *= 0.45   # slows but never negative by design
    return max(0.0, rate)

def delta_AC(age, val, coaching=1.0, ceiling=90):
    """Pitching accuracy — asymptotically approaches player ceiling."""
    distance = max(0.0, ceiling - val)
    base = coaching * (0.55 + noise(0.3)) * (distance / 45.0)
    return max(0.0, base)

def delta_ST(age, val, coaching=1.0):
    """Pitching stamina — rises early, declines from 30+."""
    if age < 26:
        return coaching * (1.1 + noise(0.5))
    elif age <= 30:
        return coaching * (0.3 + noise(0.4))
    elif age <= 33:
        return              -1.0 + noise(0.5)
    else:
        return              -2.0 + noise(0.7)

def delta_RE(age, val, coaching=1.0):
    """Pitching recovery — most coaching-sensitive; declines from 30+."""
    if age < 26:
        return coaching * (1.3 + noise(0.5))
    elif age <= 30:
        return coaching * (0.5 + noise(0.4))
    elif age <= 33:
        return              -0.8 + noise(0.5)
    else:
        return              -1.7 + noise(0.7)


# ─────────────────────────────────────────────
#  MAIN SIMULATION
# ─────────────────────────────────────────────

def age_player_career(
    name       = "TEST PLAYER",
    start_age  = 17,
    seasons    = 20,
    start_skill= 50,
    coaching   = 1.0,   # 0.8 poor | 1.0 avg | 1.2 elite
    position   = "sp",
    throws     = "R",
    bats       = "R",
    player_id  = "player_001",
    seed       = None,
):
    if seed is not None:
        random.seed(seed)

    s = {k: float(start_skill) for k in
         ['CL','SP','PO','EY','CT','BR','BU','CA','IF','OF','AR',
          'AC','ST','RE','GB','KK']}

    rows = []

    for season_idx in range(seasons):
        age = start_age + season_idx

        # ── Snapshot BEFORE this year's aging ──────────────────────────
        row = dict(
            Name=name, Age=age, Season=season_idx+1,
            PS=position, T=throws, B=bats,
            **{k: clamp(v) for k, v in s.items()},
            ID=player_id
        )
        rows.append(row)

        # ── Apply one year of aging ─────────────────────────────────────
        s['SP'] += delta_SP(age, s['SP'])
        s['PO'] += delta_PO(age, s['PO'])
        s['AR'] += delta_AR(age, s['AR'])
        s['KK'] += delta_KK(age, s['KK'])
        s['CL'] += delta_CL(age, s['CL'])
        s['EY'] += delta_EY(age, s['EY'], coaching)
        s['CT'] += delta_CT(age, s['CT'], coaching)
        s['BR'] += delta_BR(age, s['BR'], coaching)
        s['BU'] += delta_technical_up(age, s['BU'], coaching)
        s['CA'] += delta_technical_up(age, s['CA'], coaching)
        s['IF'] += delta_technical_up(age, s['IF'], coaching)
        s['OF'] += delta_technical_up(age, s['OF'], coaching)
        s['GB'] += delta_technical_up(age, s['GB'], coaching)
        s['AC'] += delta_AC(age, s['AC'], coaching)
        s['ST'] += delta_ST(age, s['ST'], coaching)
        s['RE'] += delta_RE(age, s['RE'], coaching)

        # Clamp everything to valid range
        for k in s:
            s[k] = float(clamp(s[k]))

    return rows


# ─────────────────────────────────────────────
#  OUTPUT FORMATTERS
# ─────────────────────────────────────────────

SKILL_KEYS = ['CL','SP','PO','EY','CT','BR','BU','CA','IF','OF','AR',
              'AC','ST','RE','GB','KK']

CATEGORIES = {
    'PHYSICAL':  ['SP','PO','AR','KK'],
    'COGNITIVE': ['CL','EY','BR'],
    'TECHNICAL': ['CT','BU','CA','IF','OF','AC','ST','RE','GB'],
}

CATEGORY_LABELS = {
    'CL':'Clutch','SP':'Speed', 'PO':'Power', 'EY':'Eye',  'CT':'Contact',
    'BR':'Baserun','BU':'Bunt', 'CA':'Catch', 'IF':'Infield','OF':'Outfield',
    'AR':'Arm',   'AC':'PitchAcc','ST':'Stamina','RE':'Recovery',
    'GB':'GroundBall','KK':'Strikeout',
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
    sep    = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    for row in rows:
        vals = "  ".join(f"{row[k]:>4}" for k in sk)
        print(f"{row['Age']:>4} {row['Season']:>4} | {vals}")
    print(sep)


def print_career_arcs(rows):
    """Show per-skill sparkline + start/peak/end summary."""
    print("\n── Skill Trajectories (sparkline, age 17→37) ──────────────────")
    print(f"{'Skill':<13}  {'Cat':<9}  {'Arc (17→37)':^22}  {'Start':>5}  {'Peak':>5}  {'End':>5}  {'Δ':>5}")
    print("─" * 72)

    cat_map = {}
    for cat, keys in CATEGORIES.items():
        for k in keys:
            cat_map[k] = cat[:3].capitalize()

    for k in SKILL_KEYS:
        vals = [row[k] for row in rows]
        peak = max(vals)
        label = CATEGORY_LABELS[k]
        cat   = cat_map.get(k, "   ")
        spark = sparkline(vals)
        delta = vals[-1] - vals[0]
        delta_str = f"{delta:+d}"
        print(f"{label:<13}  {cat:<9}  {spark}  {vals[0]:>5}  {peak:>5}  {vals[-1]:>5}  {delta_str:>5}")


def rows_to_csv_string(rows):
    output = io.StringIO()
    fields = ['Name','Age','Season','PS','T','B',
              'CL','SP','PO','EY','CT','BR','BU','CA','IF','OF',
              'AR','AC','ST','RE','GB','KK','ID']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # ── Run three coaching scenarios for comparison ─────────────────────
    configs = [
        ("ELITE COACHING",  1.2, 42),
        ("AVG COACHING",    1.0, 42),
        ("POOR COACHING",   0.8, 42),
    ]

    for label, coaching_val, seed_val in configs:
        print(f"\n{'═'*72}")
        print(f"  {label}  (coaching={coaching_val})  —  Age 17-37, all skills start at 50")
        print(f"{'═'*72}")

        career = age_player_career(
            name        = f"PLAYER ({label})",
            start_age   = 17,
            seasons     = 30,
            start_skill = 50,
            coaching    = coaching_val,
            position    = "sp",
            throws      = "R",
            bats        = "R",
            player_id   = f"sim_{label.lower().replace(' ','_')}",
            seed        = seed_val,
        )

        print_career_table(career)
        print_career_arcs(career)

    # ── Save average-coaching CSV ────────────────────────────────────────
    avg_career = age_player_career(
        name        = "SIM PLAYER",
        start_age   = 17,
        seasons     = 20,
        start_skill = 50,
        coaching    = 1.0,
        position    = "sp",
        throws      = "R",
        bats        = "R",
        player_id   = "sim_avg_001",
        seed        = 42,
    )

    csv_out = rows_to_csv_string(avg_career)
    path = "player_career_sim.csv"
    with open(path, "w") as f:
        f.write(csv_out)
    print(f"\nCSV saved → {path}")

