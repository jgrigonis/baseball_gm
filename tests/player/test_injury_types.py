# tests/player/test_injury_types.py
import random

import pytest

from src.player.injury_types import (
    ACTIVITIES,
    INJURY_TIERS,
    INJURY_TYPES,
    choose_injury_type,
    injury_label,
    injury_phrase,
    roll_days_missed,
)

SEVERITIES = ("minor", "moderate", "severe", "surgery")


@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("activity", ACTIVITIES)
def test_every_tier_and_activity_has_an_injury(severity, activity):
    kind = choose_injury_type(severity, activity, "1b", rng=random.Random(1))
    assert kind is not None
    assert kind.severity == severity
    assert kind.activities.get(activity, 0) > 0


def test_each_injury_lasts_inside_its_tier():
    for t in INJURY_TYPES.values():
        lo, hi = INJURY_TIERS[t.severity]
        assert lo <= t.days[0] <= t.days[1] <= hi, t.key


def test_days_come_from_the_injury_range():
    rng = random.Random(3)
    for _ in range(200):
        assert 365 <= roll_days_missed("surgery", rng, "tommy_john") <= 540
    # Untyped injuries keep rolling from the tier
    for _ in range(200):
        assert 1 <= roll_days_missed("minor", rng) <= 7


def test_pitchers_get_pitching_injuries():
    rng = random.Random(7)
    picks = {choose_injury_type("surgery", "pitching", rng=rng).key for _ in range(300)}
    assert "tommy_john" in picks
    assert "torn_acl" not in picks


def test_catchers_get_broken_fingers_and_first_basemen_do_not():
    rng = random.Random(11)
    first = {
        choose_injury_type("moderate", "fielding", "1b", rng).key for _ in range(500)
    }
    catcher = {
        choose_injury_type("moderate", "fielding", "c", rng).key for _ in range(500)
    }
    assert "broken_finger" in catcher
    assert "broken_finger" not in first


def test_position_player_tommy_john_is_mostly_hard_throwers():
    rng = random.Random(5)

    def tj(pos):
        return sum(
            choose_injury_type("surgery", "fielding", pos, rng).key == "tommy_john"
            for _ in range(3000)
        )

    assert tj("c") > 2 * tj("1b")


def test_labels_fall_back_to_severity():
    assert injury_label("torn_acl", "surgery") == "Torn ACL"
    assert injury_label(None, "moderate") == "Moderate"
    assert injury_label("no_such_injury", "minor") == "Minor"
    assert injury_phrase("tommy_john") == "Tommy John surgery"
    assert injury_phrase(None) is None
