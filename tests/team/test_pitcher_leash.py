# tests/team/test_pitcher_leash.py
"""A starter's own Starter Leash overrides the team's (Josh, 2026-11-14)."""

from src.team.manager_profile import ManagerProfile, THIRD_TIME_BATTERS


def test_a_starter_with_his_own_leash_uses_it():
    p = ManagerProfile(starter_usage="80", leashes=(("ace", "100"), ("kid", "70")))
    assert p.leash_pitches_for("ace") == 100
    assert p.leash_pitches_for("someone") == 80
    assert p.leash_pitches_for(None) == 80
    # 75 brings the third-time hook with it; the team's 85 doesn't.
    assert p.starter_hook(THIRD_TIME_BATTERS, "kid") > 1.0
    assert p.starter_hook(THIRD_TIME_BATTERS, "ace") == 1.0
    assert p.starter_hook(THIRD_TIME_BATTERS) == 1.0


def test_an_unknown_leash_falls_back_to_the_team():
    p = ManagerProfile(starter_usage="90", leashes=(("ace", "200"),))
    assert p.leash_for("ace") == "90"
