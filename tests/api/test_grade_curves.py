"""Overall ratings are graded on a curve so they spread across A+ to F."""

import collections
import random

import pytest

from scripts.calibrate_overall_grades import prospect_scores
from src.api.grade_curves import GRADES, OVERALL_CUTOFFS, overall_to_grade


@pytest.mark.parametrize("kind", OVERALL_CUTOFFS)
def test_cutoffs_cover_a_plus_to_d_minus_in_order(kind):
    cuts = OVERALL_CUTOFFS[kind]
    assert len(cuts) == len(GRADES) - 1
    assert cuts == sorted(cuts, reverse=True)
    assert len(set(cuts)) == len(cuts)


@pytest.mark.parametrize("kind", OVERALL_CUTOFFS)
def test_each_cutoff_starts_its_grade(kind):
    for cut, grade, below in zip(OVERALL_CUTOFFS[kind], GRADES, GRADES[1:]):
        assert overall_to_grade(cut, kind) == grade
        assert overall_to_grade(cut - 1, kind) == below


def test_bottom_and_missing():
    assert overall_to_grade(0, "hitter") == "F"
    assert overall_to_grade(None, "prospect") == "?"


def test_a_draft_class_spreads_across_the_grades():
    scores = prospect_scores(2, random.Random(7))
    counts = collections.Counter(overall_to_grade(s, "prospect") for s in scores)
    share = {g: counts[g] / len(scores) for g in GRADES}

    assert share["A-"] + share["A"] + share["A+"] > 0.005
    assert share["D+"] + share["D"] + share["D-"] + share["F"] > 0.10
    assert max(share.values()) < 0.25
