# tests/test_player_evaluator.py
"""
✔ Evaluator is pure, deterministic, mapping-only
✔ Skills normalization happens once, at creation
✔ Guard test enforces interface, not data shape
✔ No defensive clutter in evaluator logic
"""
# import copy
# import pytest

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS



def skills(**overrides):
    """
    Create a PlayerSkills object with sane defaults,
    overridden per test.
    """
    base = {k: 50 for k in SKILLS}
    base.update(overrides)
    return PlayerSkills(base)

def test_rate_player_is_deterministic():
    """Determinism & purity"""
    s = skills(speed=80, contact=60)

    r1 = PlayerEvaluator.rate_player(s)
    r2 = PlayerEvaluator.rate_player(s)

    assert r1 == r2


def test_rate_player_does_not_mutate_skills():
    """Determinism & purity"""
    s = skills(speed=80, contact=60)
    before = s.as_dict()

    PlayerEvaluator.rate_player(s)

    assert s.as_dict() == before
def test_all_expected_roles_are_present():
    """Ratings existence & bounds"""
    s = skills()
    ratings = PlayerEvaluator.rate_player(s)

    expected = {
        "cf", "rf", "lf", "c", "1b", "2b", "ss", "3b", "p",
        "lead_off", "contact_hitter", "power_hitter",
        "speed_runner", "overall_offense", "overall_player",
    }

    assert expected.issubset(ratings.keys())


def test_all_ratings_are_clamped_to_0_100():
    """Ratings existence & bounds"""
    s = skills(**{k: 999 for k in SKILLS})
    ratings = PlayerEvaluator.rate_player(s)

    for value in ratings.values():
        assert 0 <= value <= 100

def test_speed_impacts_cf_more_than_1b():
    """
    Role weighting behavior (relative, stable tests)
    Speed matters more for CF than 1B
    """
    slow = skills(speed=30)
    fast = skills(speed=90)

    r_slow = PlayerEvaluator.rate_player(slow)
    r_fast = PlayerEvaluator.rate_player(fast)

    assert r_fast["cf"] > r_slow["cf"]
    assert (r_fast["cf"] - r_slow["cf"]) > (r_fast["1b"] - r_slow["1b"])

def test_power_vs_contact_hitters():
    """Power vs contact roles"""
    contact_guy = skills(power=30, contact=90)
    slugger = skills(power=90, contact=30)

    r_contact = PlayerEvaluator.rate_player(contact_guy)
    r_slugger = PlayerEvaluator.rate_player(slugger)

    assert r_slugger["power_hitter"] > r_contact["power_hitter"]
    assert r_contact["contact_hitter"] > r_slugger["contact_hitter"]

def test_power_hitter_emphasizes_power():
    """Power vs contact roles"""
    weak = skills(power=30, contact=70)
    slugger = skills(power=90, contact=30)

    r_weak = PlayerEvaluator.rate_player(weak)
    r_slugger = PlayerEvaluator.rate_player(slugger)

    assert r_slugger["power_hitter"] > r_weak["power_hitter"]
    assert r_weak["contact_hitter"] > r_slugger["contact_hitter"]

def test_overall_player_uses_best_defensive_skill_only():
    """Critical test: overall_player uses max(IF, OF, C)"""
    infielder = skills(infield=90, outfield=10, catching=10)
    outfielder = skills(infield=10, outfield=90, catching=10)
    catcher = skills(infield=10, outfield=10, catching=90)

    r_i = PlayerEvaluator.rate_player(infielder)["overall_player"]
    r_o = PlayerEvaluator.rate_player(outfielder)["overall_player"]
    r_c = PlayerEvaluator.rate_player(catcher)["overall_player"]

    assert r_i == r_o == r_c


def test_arm_contributes_to_overall_player():
    """Arm contributes to overall_player"""
    weak_arm = skills(arm=20)
    cannon = skills(arm=90)

    r_weak = PlayerEvaluator.rate_player(weak_arm)["overall_player"]
    r_cannon = PlayerEvaluator.rate_player(cannon)["overall_player"]

    assert r_cannon > r_weak


def test_overall_player_rewards_well_rounded_players():
    """Well-rounded players beat specialists"""
    specialist = skills(
        power=95, speed=20, infield=20, outfield=20, catching=20
    )
    all_around = skills(
        power=70, speed=70, infield=70, outfield=70, catching=70
    )

    r_spec = PlayerEvaluator.rate_player(specialist)["overall_player"]
    r_all = PlayerEvaluator.rate_player(all_around)["overall_player"]

    assert r_all > r_spec

def test_player_evaluator_uses_mapping_access_only():
    """
    The One-Line Guard Test
    Use PlayerSkills.from_row({}), which guarantees all keys exist 
    with zero values
    """
    PlayerEvaluator.rate_player(PlayerSkills.from_row({}))

