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

OverallKind = Literal["prospect", "hitter", "pitcher"]

# The lowest score that earns each grade from A+ down to D-; anything lower
# is an F. Regenerate with scripts/calibrate_overall_grades.py.
OVERALL_CUTOFFS: dict[str, list[int]] = {
    # Draft classes. A+ is about 1 in 1,000, so roughly one every other class.
    "prospect": [75, 70, 66, 63, 60, 57, 54, 52, 49, 47, 44, 42],
    # Position players on opening-day 26-man rosters: a typical big leaguer is
    # a C+ or C, like the 50 on a 20-80 scouting scale.
    "hitter": [74, 71, 68, 66, 63, 61, 58, 56, 53, 51, 49, 46],
    # SP/RP on the same rosters, rated max(sp, rp).
    "pitcher": [78, 74, 71, 68, 66, 63, 60, 58, 55, 52, 50, 47],
}


def overall_to_grade(raw: float | None, kind: OverallKind) -> str:
    """The curved letter grade for an overall rating of the given kind."""
    if raw is None:
        return "?"
    for cut, grade in zip(OVERALL_CUTOFFS[kind], GRADES):
        if raw >= cut:
            return grade
    return "F"
