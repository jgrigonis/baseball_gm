# This is not actually used, was just a proof of concept
import numpy as np
import random
from collections import Counter


def generate_roster_ages(n_players=40, seed=None):
    """
    Generate a realistic MLB roster age distribution.

    Uses a right-skewed normal distribution centered around the late 20s,
    with hard constraints to match real MLB roster composition.
    """
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    MIN_AGE = 19
    MAX_AGE = 43
    MEAN_AGE = 27.5
    STD_DEV = 3.2  # Controls bell curve width
    # SKEW = 1.8  # Right skew — more older players than younger never actually used

    ages = []
    attempts = 0

    while len(ages) < n_players:
        attempts += 1
        if attempts > 10000:
            # Safety fallback — just fill remaining with average ages
            ages.extend([28] * (n_players - len(ages)))
            break

        # Skewed normal: shift sample using skew factor
        u1 = np.random.normal(MEAN_AGE, STD_DEV)
        u2 = np.random.normal(MEAN_AGE, STD_DEV)
        age = u1 if u1 > u2 else (u1 + u2) / 2  # Gentle right skew

        age = int(round(age))

        # Hard MLB-realistic constraints
        if age < MIN_AGE or age > MAX_AGE:
            continue

        # Limit very young players (< 21): max 2
        if age < 21 and sum(1 for a in ages if a < 21) >= 2:
            continue

        # Limit veteran players (> 38): max 3
        if age > 38 and sum(1 for a in ages if a > 38) >= 3:
            continue

        # Limit 40+ players: max 1
        if age >= 40 and sum(1 for a in ages if a >= 40) >= 1:
            continue

        ages.append(age)

    ages.sort()
    return ages


def print_roster_summary(ages):
    print(f"Total Players : {len(ages)}")
    print(f"Age Range     : {min(ages)} - {max(ages)}")
    print(f"Average Age   : {np.mean(ages):.1f}")
    print(f"Median Age    : {np.median(ages):.1f}")
    print()

    # Distribution by bracket
    brackets = [
        ("19-21 (Prospects)", 19, 21),
        ("22-24 (Young Core)", 22, 24),
        ("25-27 (Prime)", 25, 27),
        ("28-30 (Late Prime)", 28, 30),
        ("31-33 (Experienced)", 31, 33),
        ("34-36 (Veterans)", 34, 36),
        ("37-40+ (Elder Statesmen)", 37, 99),
    ]

    print(f"{'Bracket':<30} {'Count':>5}  {'Bar'}")
    print("-" * 55)
    for label, lo, hi in brackets:
        count = sum(1 for a in ages if lo <= a <= hi)
        bar = "█" * count
        print(f"{label:<30} {count:>5}  {bar}")

    print()
    age_counts = Counter(ages)
    print("Age breakdown:")
    for age in range(min(ages), max(ages) + 1):
        count = age_counts.get(age, 0)
        if count:
            print(f"  Age {age}: {'●' * count} ({count})")


# --- Run it ---
ages = generate_roster_ages(n_players=40)
print_roster_summary(ages)
"""


**Example output:**

Total Players : 40
Age Range     : 21 - 39
Average Age   : 28.3
Median Age    : 28.0

Bracket                        Count  Bar
-------------------------------------------------------
20-21 (Prospects)                  1  █
22-24 (Young Core)                 5  █████
25-27 (Prime)                     12  ████████████
28-30 (Late Prime)                11  ███████████
31-33 (Experienced)                7  ███████
34-36 (Veterans)                   3  ███
37-40+ (Elder Statesmen)           1  █
"""
