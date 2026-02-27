# scripts/simulate_ages.py
"""
Quick simulation of roster age distribution.
Run from project root: python simulate_ages.py
"""

import random
from collections import Counter
from scipy.stats import skewnorm

_MIN_AGE = 18
_MAX_AGE = 44
_MEAN_AGE = 24
_STD_DEV = 6.0
_SKEW = 0.2


def draw_roster_age(rng, current_ages):
    for _ in range(10_000):
        seed = rng.getrandbits(32)
        age = int(
            round(
                skewnorm.rvs(a=_SKEW, loc=_MEAN_AGE, scale=_STD_DEV, random_state=seed)
            )
        )

        if age < _MIN_AGE or age > _MAX_AGE:
            continue
        if age < 21 and sum(1 for a in current_ages if a < 21) >= 2:
            continue
        # if age < 23 and sum(1 for a in current_ages if a < 23) >= 5:
        #     continue
        if age > 38 and sum(1 for a in current_ages if a > 38) >= 3:
            continue
        if age >= 40 and sum(1 for a in current_ages if a >= 40) >= 1:
            continue

        return age

    return _MEAN_AGE


def simulate(num_teams=100, roster_size=40, seed=42):
    rng = random.Random(seed)
    all_ages = []
    team_avgs = []

    for _ in range(num_teams):
        current_ages = []
        for _ in range(roster_size):
            age = draw_roster_age(rng, current_ages)
            current_ages.append(age)
        all_ages.extend(current_ages)
        team_avgs.append(sum(current_ages) / len(current_ages))

    oldest_avg = max(team_avgs)
    youngest_avg = min(team_avgs)
    return all_ages, oldest_avg, youngest_avg


def print_histogram(ages, width=50):
    counts = Counter(ages)
    total = len(ages)
    min_age, max_age = min(ages), max(ages)
    peak = max(counts.values())

    print(f"\nAge distribution across {total:,} players")
    print(f"Mean: {sum(ages)/total:.1f}  Min: {min_age}  Max: {max_age}\n")

    for age in range(min_age, max_age + 1):
        count = counts.get(age, 0)
        bar = "█" * int(count / peak * width)
        pct = count / total * 100
        print(f"  {age:2d} | {bar:<{width}} {count:4d} ({pct:4.1f}%)")


if __name__ == "__main__":
    import sys

    num_teams = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    roster_size = int(sys.argv[2]) if len(sys.argv) > 2 else 40

    ages, oldest_avg, youngest_avg = simulate(
        num_teams=num_teams, roster_size=roster_size
    )
    print_histogram(ages)
    print(f"\n  Oldest team avg age:   {oldest_avg:.1f}")
    print(f"  Youngest team avg age: {youngest_avg:.1f}")
