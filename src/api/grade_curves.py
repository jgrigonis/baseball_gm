# src/api/grade_curves.py
"""
Curved letter grades for overall ratings.

A single skill (contact, power, stuff...) spreads widely, so it is graded on
the plain scale in schemas.skill_to_grade: every 5 points is a grade. An
overall rating averages many skills, which cancels out a player's highs and
lows, so on that scale nearly everyone lands between B and C. Overall ratings
are graded on a curve instead, one per kind of overall, so that A+ is rare
but real and D and F show up.

The cutoffs come from scripts/calibrate_overall_grades.py, which simulates
each population and sets the curve's target share for every grade. Only the
letter a GM sees changes: the sim, the AI and the draft all use the raw
numbers.
"""

from typing import Literal

GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]

OverallKind = Literal[
    "prospect",
    "hitter",
    "pitcher",
    "team_lineup",
    "team_rotation",
    "team_bullpen",
    "team_defense",
    "team_power",
    "team_speed",
]

# The lowest score that earns each grade from A+ down to D-; anything lower
# is an F. Regenerate with scripts/calibrate_overall_grades.py.
OVERALL_CUTOFFS: dict[str, list[float]] = {
    # Draft classes. A+ is about 1 in 1,000, so roughly one every other class.
    "prospect": [75, 70, 66, 63, 60, 57, 54, 52, 49, 47, 44, 42],
    # Position players on opening-day 26-man rosters: a typical big leaguer is
    # a C+ or C, like the 50 on a 20-80 scouting scale.
    "hitter": [74, 71, 68, 66, 63, 61, 58, 56, 53, 51, 49, 46],
    # SP/RP on the same rosters, rated max(sp, rp).
    "pitcher": [78, 74, 71, 68, 66, 63, 60, 58, 55, 52, 50, 47],
    # Team areas on the welcome screen's scouting report, from the same
    # opening-day rosters (welcome.area_scores). Averaging a whole staff or
    # lineup bunches these even tighter, so every team used to grade B. They use a
    # flatter curve (about 2% A+), so most leagues have a team or two at each end.
    "team_lineup": [
        62.9,
        62.2,
        61.4,
        60.9,
        60.2,
        59.7,
        59.1,
        58.4,
        57.9,
        57.2,
        56.6,
        55.8,
    ],
    "team_rotation": [
        68.8,
        67.2,
        66.2,
        65.3,
        64.4,
        63.6,
        62.8,
        61.8,
        61.0,
        60.0,
        58.6,
        57.2,
    ],
    "team_bullpen": [
        64.6,
        63.1,
        61.6,
        60.4,
        59.4,
        58.4,
        57.6,
        56.6,
        55.6,
        54.4,
        53.3,
        51.7,
    ],
    "team_defense": [
        72.6,
        71.8,
        70.7,
        70.0,
        69.3,
        68.7,
        67.9,
        67.2,
        66.4,
        65.8,
        65.0,
        63.7,
    ],
    "team_power": [
        67.8,
        65.7,
        64.1,
        62.6,
        61.2,
        59.9,
        58.4,
        56.9,
        55.6,
        53.9,
        52.1,
        49.8,
    ],
    "team_speed": [
        65.4,
        63.0,
        61.2,
        59.9,
        58.6,
        57.0,
        55.7,
        54.2,
        52.7,
        51.2,
        49.8,
        47.6,
    ],
}


def overall_to_grade(raw: float | None, kind: OverallKind) -> str:
    """The curved letter grade for an overall rating of the given kind."""
    if raw is None:
        return "?"
    for cut, grade in zip(OVERALL_CUTOFFS[kind], GRADES):
        if raw >= cut:
            return grade
    return "F"


# Role and position ratings (SP, RP, CP, the hitter roles, each fielding
# position and best defense) are composites too, so on the plain scale they
# bunch: nearly every starter graded B or C+, and nearly every shortstop A- or
# B+ at short. Each is graded on a curve against the players who fill that
# role (SP against starters, SS against shortstops, IF against infielders, the
# hitter roles and best defense against every position player), with the
# same shares as hitters. A grade from another role's pool reads the same way: a
# first baseman's SS grade says how he'd rank among shortstops.
# Regenerate with scripts/calibrate_overall_grades.py.
ROLE_CUTOFFS: dict[str, list[float]] = {
    "sp": [78, 74, 71, 68, 65, 62, 60, 57, 54, 51, 48, 45],
    "rp": [76, 73, 69, 66, 63, 59, 56, 53, 50, 48, 44, 41],
    "cp": [77, 74, 70, 66, 63, 60, 56, 53, 50, 46, 43, 39],
    "lead_off": [81, 77, 74, 70, 66, 63, 59, 56, 52, 49, 45, 41],
    "contact_hitter": [85, 80, 76, 71, 67, 63, 59, 55, 51, 47, 43, 37],
    "power_hitter": [82, 77, 73, 69, 64, 60, 56, 51, 47, 43, 39, 35],
    "overall_offense": [75, 71, 68, 65, 62, 59, 56, 53, 50, 48, 45, 42],
    "best_def": [88, 84, 80, 77, 74, 70, 67, 64, 61, 58, 55, 52],
    "c": [87, 83, 80, 77, 74, 71, 68, 65, 62, 59, 56, 53],
    "1b": [85, 80, 76, 72, 67, 62, 58, 53, 49, 44, 40, 32],
    "2b": [88, 85, 81, 78, 76, 73, 70, 67, 65, 62, 60, 57],
    "3b": [85, 82, 78, 74, 71, 67, 64, 60, 57, 54, 50, 47],
    "ss": [83, 81, 79, 76, 74, 71, 69, 66, 64, 62, 59, 57],
    "lf": [83, 79, 76, 73, 70, 66, 64, 60, 57, 54, 51, 48],
    "cf": [83, 80, 77, 74, 72, 70, 67, 65, 62, 60, 57, 54],
    "rf": [81, 79, 76, 74, 71, 68, 65, 62, 59, 56, 53, 50],
    "if": [87, 83, 80, 77, 74, 71, 67, 64, 60, 57, 54, 50],
    "of": [83, 80, 77, 74, 71, 68, 65, 62, 59, 56, 53, 50],
}

# Anything without a curve stays on the plain scale, 5 points a grade.
_PLAIN_CUTOFFS = [80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25]


def role_to_grade(raw: float | None, role: str) -> str:
    """The curved letter grade for a role or position rating."""
    if raw is None:
        return "?"
    for cut, grade in zip(ROLE_CUTOFFS.get(role, _PLAIN_CUTOFFS), GRADES):
        if raw >= cut:
            return grade
    return "F"
