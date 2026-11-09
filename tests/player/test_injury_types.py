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
    roll_rust,
    rust_days_to_clear,
    rust_left,
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


# ── Rust ──────────────────────────────────────────────────────────────────────


def test_every_injury_has_rust_on_real_skills():
    from src.player.injury_types import RUST
    from src.player.skill_map import SKILL_MAP

    assert set(RUST) == set(INJURY_TYPES)
    for days, amounts in RUST.values():
        assert days > 0
        assert set(amounts) <= set(SKILL_MAP.values())


def test_rust_is_rolled_within_its_bounds():
    rng = random.Random(2)
    for _ in range(300):
        skills, length = roll_rust("hamstring_strain", 20, rng=rng)
        assert 2.5 <= skills["speed"] <= 5
        assert 1.5 <= skills["base_running"] <= 3
        # 21 days × 50-150% × 0.8-1.2 for how long the injury ran
        assert 21 * 0.5 * 0.8 - 0.1 <= length <= 21 * 1.5 * 1.2 + 0.1
    assert roll_rust(None, 5) is None


def _mean_length(**kw):
    rng = random.Random(9)
    return sum(roll_rust("torn_acl", rng=rng, **kw)[1] for _ in range(500)) / 500


def test_rust_lasts_longer_after_a_long_layoff_and_for_older_players():
    assert _mean_length(days_missed=400) > _mean_length(days_missed=270)
    assert _mean_length(days_missed=300, age=36) > _mean_length(days_missed=300, age=24)


def test_durable_hitters_shake_rust_faster():
    assert _mean_length(days_missed=300, durability=90) < _mean_length(
        days_missed=300, durability=20
    )


def test_rust_fades_twice_as_fast_on_days_off():
    skills = {"speed": 4.0}
    # Ten days back playing every day: half of a 20-day rust is gone
    assert rust_left(skills, 20, 10, 10) == {"speed": 2.0}
    # Ten days back resting every day: all of it is gone
    assert rust_left(skills, 20, 10, 0) == {}
    # Five days rested count as much as ten played
    assert rust_left(skills, 20, 5, 0) == rust_left(skills, 20, 10, 10)


def test_days_to_clear_counts_to_the_last_whole_point():
    # 4 points over 20 days: under half a point after 17.5 days of play
    assert rust_days_to_clear({"speed": 4.0}, 20, 0, 0) == 18
    assert rust_days_to_clear({"speed": 4.0}, 20, 10, 10) == 8
    assert rust_days_to_clear({"speed": 4.0}, 20, 30, 30) == 0


# ── Lasting effects ──────────────────────────────────────────────────────────

from src.player.injury_types import (  # noqa: E402
    LASTING,
    OUTCOME_LABELS,
    cap_drop_chance,
    effects_text,
    outcome_odds,
    roll_lasting,
)


def test_every_lasting_table_is_a_known_injury_with_labelled_outcomes():
    for key, outcomes in LASTING.items():
        assert key in INJURY_TYPES
        for o in outcomes:
            assert o.key in OUTCOME_LABELS
            for lo, hi in o.effects.values():
                assert lo <= hi


def test_minor_injuries_leave_nothing():
    assert roll_lasting("blister", pitcher=True, age=28) is None
    assert roll_lasting(None, pitcher=False, age=28) is None


def test_odds_sum_to_one_and_age_moves_them_from_best_to_worst():
    prime = dict((o.key, p) for o, p in outcome_odds("tommy_john", age=27))
    old = dict((o.key, p) for o, p in outcome_odds("tommy_john", age=35))
    young = dict((o.key, p) for o, p in outcome_odds("tommy_john", age=22))
    for odds in (prime, old, young):
        assert sum(odds.values()) == pytest.approx(1)
    assert prime == pytest.approx({"stronger": 0.25, "full": 0.55, "bad": 0.20})
    assert old["stronger"] == pytest.approx(0.10)
    assert old["bad"] == pytest.approx(0.35)
    assert young["stronger"] == pytest.approx(0.34)
    assert young["bad"] == pytest.approx(0.11)


def test_durable_hitters_heal_better():
    tough = dict((o.key, p) for o, p in outcome_odds("torn_acl", 28, durability=100))
    frail = dict((o.key, p) for o, p in outcome_odds("torn_acl", 28, durability=0))
    assert tough["full"] > 0.15 > frail["full"]


def test_tommy_john_outcomes_over_many_rolls():
    rng = random.Random(7)
    rolls = [roll_lasting("tommy_john", True, 28, rng=rng) for _ in range(4000)]
    share = {
        k: sum(r.outcome == k for r in rolls) / len(rolls)
        for k in ("stronger", "full", "bad")
    }
    assert share["stronger"] == pytest.approx(0.25, abs=0.03)
    assert share["bad"] == pytest.approx(0.20, abs=0.03)
    for r in rolls:
        if r.outcome == "stronger":
            assert 2 <= r.effects["strikes"] <= 5 and 1 <= r.effects["arm"] <= 3
        if r.outcome == "bad":
            assert -8 <= r.effects["strikes"] <= -3


def test_pitchers_back_trouble_hits_stamina_and_can_cost_durability():
    rng = random.Random(3)
    seen = set()
    for _ in range(500):
        r = roll_lasting("back_surgery", pitcher=True, age=33, durability=50, rng=rng)
        assert "power" not in r.effects
        seen |= set(r.effects)
    assert seen == {"stamina", "durability"}


def test_durability_moves_a_pitchers_odds_like_a_hitters():
    assert outcome_odds("torn_acl", 30, 99) != outcome_odds("torn_acl", 30, 1)
    assert cap_drop_chance(30, 99) < cap_drop_chance(30, 1)


def test_a_position_players_arm_takes_the_pitching_damage():
    rng = random.Random(4)
    seen = set()
    for _ in range(300):
        r = roll_lasting("torn_rotator_cuff", pitcher=False, age=29, rng=rng)
        seen |= set(r.effects)
    assert seen == {"arm"}


def test_cap_drop_is_about_one_in_ten_and_worse_with_age():
    assert cap_drop_chance(30, None) == pytest.approx(0.10)
    assert cap_drop_chance(22, None) == pytest.approx(0.05)
    assert cap_drop_chance(38, None) == pytest.approx(0.18)
    assert cap_drop_chance(30, 100) < cap_drop_chance(30, 50) < cap_drop_chance(30, 0)


def test_only_losses_can_drop_the_cap():
    rng = random.Random(11)
    for _ in range(2000):
        r = roll_lasting("tommy_john", True, 40, rng=rng)
        if r.cap_drop:
            assert any(v < 0 for v in r.effects.values())


def test_effects_text():
    assert effects_text({"speed": -4, "base_running": -2}) == "SP −4 · BR −2"
    assert effects_text({"strikes": 3}) == "KK +3"
    assert effects_text({}) == ""
