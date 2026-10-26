# tests/player/test_player_development.py
"""
Regression test for the shape of a career: drafted players should keep
improving into their late 20s, not peak at draft age.

Ages a cohort of draft-age prospects one year at a time, saving and
reloading skills between years the way the offseason pipeline does, and
checks how much they improve.
"""

import random
import statistics

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_factory import PlayerFactory
from src.player.player_skills import PlayerSkills

DRAFT_AGE = 21
COHORT_SIZE = 300
POSITIONS = ["sp", "rp", "c", "1b", "2b", "ss", "3b", "lf", "cf", "rf"]


def _rating(skills: PlayerSkills, position: str) -> int:
    ratings = PlayerEvaluator.rate_player(skills)
    return ratings["p"] if position in ("sp", "rp") else ratings["overall_player"]


def _career(seed: int) -> list[tuple[int, dict[int, int]]]:
    """(prospect rating at draft, {age: rating}) for each player in the cohort."""
    rng = random.Random(seed)
    factory = PlayerFactory(rng=rng)
    careers = []
    for i in range(COHORT_SIZE):
        position = POSITIONS[i % len(POSITIONS)]
        player = factory.create(position=position)
        skills = player.skills.age_to(DRAFT_AGE, rng=rng, caps=player.caps)
        prospect = PlayerEvaluator.prospect_rating(skills)
        ratings = {}
        for age in range(DRAFT_AGE, 34):
            ratings[age] = _rating(skills, position)
            aged = skills.age_to(age + 1, from_age=age, rng=rng, caps=player.caps)
            # Round-trip through whole numbers + fractions, as the DB does
            skills = PlayerSkills(aged.as_dict(), age=aged.age).with_fractions(
                aged.fractions()
            )
        careers.append((prospect, ratings))
    return careers


CAREERS = _career(seed=7)


def test_cohort_improves_from_draft_to_late_twenties():
    gains = [r[27] - r[DRAFT_AGE] for _, r in CAREERS]
    assert statistics.mean(gains) >= 4


def test_cohort_peaks_in_late_twenties():
    peaks = [max(r, key=r.get) for _, r in CAREERS]
    assert 26 <= statistics.median(peaks) <= 31


def test_top_prospects_still_develop():
    """The best prospects are the ones who used to stop improving."""
    top = sorted(CAREERS, key=lambda c: -c[0])[: COHORT_SIZE // 10]
    no_better = sum(r[28] <= r[DRAFT_AGE] for _, r in top)
    assert no_better / len(top) < 0.1
    assert statistics.mean(r[28] - r[DRAFT_AGE] for _, r in top) >= 3
