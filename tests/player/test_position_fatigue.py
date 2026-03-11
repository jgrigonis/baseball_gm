# tests/player/test_position_fatigue.py

import pytest
from src.player.position_fatigue import (
    FatigueLevel,
    PositionPlayerFatigue,
    POSITION_DRAIN_RATES,
    REST_RECOVERY_RATE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def catcher():
    return PositionPlayerFatigue(position="C", durability=50)

@pytest.fixture
def outfielder():
    return PositionPlayerFatigue(position="LF", durability=50)

@pytest.fixture
def dh():
    return PositionPlayerFatigue(position="DH", durability=50)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_defaults_to_fresh(self, catcher):
        assert catcher.energy == 1.0
        assert catcher.get_level() == FatigueLevel.FRESH

    def test_invalid_durability_raises(self):
        with pytest.raises(ValueError, match="Durability must be positive"):
            PositionPlayerFatigue(position="C", durability=0)

    def test_negative_durability_raises(self):
        with pytest.raises(ValueError, match="Durability must be positive"):
            PositionPlayerFatigue(position="C", durability=-10)

    def test_invalid_position_raises(self):
        with pytest.raises(ValueError, match="Unknown position"):
            PositionPlayerFatigue(position="P", durability=50)

    def test_consecutive_days_starts_at_zero(self, catcher):
        assert catcher.consecutive_days == 0

    def test_season_games_starts_at_zero(self, catcher):
        assert catcher.season_games_played == 0


# ---------------------------------------------------------------------------
# Fatigue levels
# ---------------------------------------------------------------------------

class TestFatigueLevels:
    def test_fresh_at_full_energy(self, catcher):
        catcher.set_energy(1.0)
        assert catcher.get_level() == FatigueLevel.FRESH

    def test_fresh_at_threshold(self, catcher):
        catcher.set_energy(0.85)
        assert catcher.get_level() == FatigueLevel.FRESH

    def test_good_below_fresh(self, catcher):
        catcher.set_energy(0.84)
        assert catcher.get_level() == FatigueLevel.GOOD

    def test_good_at_threshold(self, catcher):
        catcher.set_energy(0.65)
        assert catcher.get_level() == FatigueLevel.GOOD

    def test_tired_below_good(self, catcher):
        catcher.set_energy(0.64)
        assert catcher.get_level() == FatigueLevel.TIRED

    def test_tired_at_threshold(self, catcher):
        catcher.set_energy(0.40)
        assert catcher.get_level() == FatigueLevel.TIRED

    def test_exhausted_below_tired(self, catcher):
        catcher.set_energy(0.39)
        assert catcher.get_level() == FatigueLevel.EXHAUSTED

    def test_exhausted_at_threshold(self, catcher):
        catcher.set_energy(0.01)
        assert catcher.get_level() == FatigueLevel.EXHAUSTED

    def test_zero_below_exhausted(self, catcher):
        catcher.set_energy(0.0)
        assert catcher.get_level() == FatigueLevel.ZERO


# ---------------------------------------------------------------------------
# play_game
# ---------------------------------------------------------------------------

class TestPlayGame:
    def test_energy_decreases_after_game(self, catcher):
        before = catcher.energy
        catcher.play_game()
        assert catcher.energy < before

    def test_consecutive_days_increments(self, catcher):
        catcher.play_game()
        assert catcher.consecutive_days == 1
        catcher.play_game()
        assert catcher.consecutive_days == 2

    def test_season_games_increments(self, catcher):
        catcher.play_game()
        catcher.play_game()
        assert catcher.season_games_played == 2

    def test_partial_game_drains_less(self, catcher):
        full = PositionPlayerFatigue(position="C", durability=50)
        partial = PositionPlayerFatigue(position="C", durability=50)
        full.play_game(innings_played=9)
        partial.play_game(innings_played=3)
        assert partial.energy > full.energy

    def test_innings_capped_at_nine(self, catcher):
        normal = PositionPlayerFatigue(position="C", durability=50)
        overcapped = PositionPlayerFatigue(position="C", durability=50)
        normal.play_game(innings_played=9)
        overcapped.play_game(innings_played=15)
        assert normal.energy == overcapped.energy

    def test_energy_never_goes_below_zero(self, catcher):
        catcher.set_energy(0.0)
        catcher.play_game()
        assert catcher.energy == 0.0

    def test_higher_durability_drains_less(self):
        avg = PositionPlayerFatigue(position="C", durability=50)
        elite = PositionPlayerFatigue(position="C", durability=80)
        avg.play_game()
        elite.play_game()
        assert elite.energy > avg.energy

    def test_streak_penalty_kicks_in_after_four(self, catcher):
        # Play 5 games — penalty starts on game 6 (consecutive_games == 5)
        drain_per_game = []
        for _ in range(8):
            before = catcher.energy
            catcher.play_game()
            drain_per_game.append(before - catcher.energy)

        # First 4 games should have no streak penalty
        assert drain_per_game[0] == pytest.approx(drain_per_game[1])
        assert drain_per_game[0] == pytest.approx(drain_per_game[3])

        # Game 6+ should drain more than game 1
        assert drain_per_game[5] > drain_per_game[0]
        assert drain_per_game[6] > drain_per_game[5]

    def test_catcher_drains_faster_than_outfielder(self):
        c = PositionPlayerFatigue(position="C", durability=50)
        lf = PositionPlayerFatigue(position="LF", durability=50)
        c.play_game()
        lf.play_game()
        assert c.energy < lf.energy

    def test_dh_drains_slowest(self, dh, catcher):
        dh.play_game()
        catcher.play_game()
        assert dh.energy > catcher.energy


# ---------------------------------------------------------------------------
# rest_day
# ---------------------------------------------------------------------------

class TestRestDay:
    def test_energy_increases_on_rest(self, catcher):
        catcher.set_energy(0.5)
        catcher.rest_day()
        assert catcher.energy > 0.5

    def test_consecutive_days_resets_on_rest(self, catcher):
        catcher.play_game()
        catcher.play_game()
        catcher.rest_day()
        assert catcher.consecutive_days == 0

    def test_energy_never_exceeds_one(self, catcher):
        catcher.set_energy(0.99)
        catcher.rest_day()
        assert catcher.energy <= 1.0

    def test_multiple_rest_days_recover_more(self, catcher):
        catcher.set_energy(0.5)
        one_day = PositionPlayerFatigue(position="C", durability=50)
        one_day.set_energy(0.5)
        two_day = PositionPlayerFatigue(position="C", durability=50)
        two_day.set_energy(0.5)

        one_day.rest_day(days=1)
        two_day.rest_day(days=2)
        assert two_day.energy > one_day.energy

    def test_rest_at_full_energy_stays_at_one(self, catcher):
        catcher.set_energy(1.0)
        catcher.rest_day()
        assert catcher.energy == pytest.approx(1.0)

    def test_diminishing_returns_on_rest(self, catcher):
        """Second rest day recovers less than the first."""
        catcher.set_energy(0.4)

        day1 = PositionPlayerFatigue(position="C", durability=50)
        day1.set_energy(0.4)
        day1.rest_day(days=1)
        gain_day1 = day1.energy - 0.4

        day2 = PositionPlayerFatigue(position="C", durability=50)
        day2.set_energy(day1.energy)
        day2.rest_day(days=1)
        gain_day2 = day2.energy - day1.energy

        assert gain_day1 > gain_day2


# ---------------------------------------------------------------------------
# end_season
# ---------------------------------------------------------------------------

class TestEndSeason:
    def test_energy_resets_to_full(self, catcher):
        catcher.set_energy(0.3)
        catcher.end_season()
        assert catcher.energy == 1.0

    def test_consecutive_days_resets(self, catcher):
        for _ in range(10):
            catcher.play_game()
        catcher.end_season()
        assert catcher.consecutive_days == 0

    def test_season_games_resets(self, catcher):
        for _ in range(10):
            catcher.play_game()
        catcher.end_season()
        assert catcher.season_games_played == 0


# ---------------------------------------------------------------------------
# get_stat_modifier
# ---------------------------------------------------------------------------

class TestStatModifier:
    def test_fresh_has_bonus(self, catcher):
        catcher.set_energy(1.0)
        assert catcher.get_stat_modifier() > 1.0

    def test_good_is_neutral(self, catcher):
        catcher.set_energy(0.70)
        assert catcher.get_stat_modifier() == pytest.approx(1.0)

    def test_tired_penalizes(self, catcher):
        catcher.set_energy(0.50)
        assert catcher.get_stat_modifier() < 1.0

    def test_exhausted_penalizes_more_than_tired(self, catcher):
        catcher.set_energy(0.50)
        tired_mod = catcher.get_stat_modifier()
        catcher.set_energy(0.20)
        exhausted_mod = catcher.get_stat_modifier()
        assert exhausted_mod < tired_mod

    def test_zero_has_largest_penalty(self, catcher):
        catcher.set_energy(0.0)
        assert catcher.get_stat_modifier() == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# get_injury_risk_multiplier
# ---------------------------------------------------------------------------

class TestInjuryRiskMultiplier:
    def test_fresh_reduces_risk(self, catcher):
        catcher.set_energy(1.0)
        assert catcher.get_injury_risk_multiplier() < 1.0

    def test_good_is_baseline(self, catcher):
        catcher.set_energy(0.70)
        assert catcher.get_injury_risk_multiplier() == pytest.approx(1.0)

    def test_tired_increases_risk(self, catcher):
        catcher.set_energy(0.50)
        assert catcher.get_injury_risk_multiplier() > 1.0

    def test_risk_increases_with_fatigue(self, catcher):
        catcher.set_energy(0.70)
        good_risk = catcher.get_injury_risk_multiplier()
        catcher.set_energy(0.50)
        tired_risk = catcher.get_injury_risk_multiplier()
        catcher.set_energy(0.20)
        exhausted_risk = catcher.get_injury_risk_multiplier()
        assert good_risk < tired_risk < exhausted_risk

    def test_zero_has_highest_risk(self, catcher):
        catcher.set_energy(0.0)
        assert catcher.get_injury_risk_multiplier() == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# set_energy
# ---------------------------------------------------------------------------

class TestSetEnergy:
    def test_sets_valid_energy(self, catcher):
        catcher.set_energy(0.5)
        assert catcher.energy == pytest.approx(0.5)

    def test_clamps_above_one(self, catcher):
        catcher.set_energy(1.5)
        assert catcher.energy == pytest.approx(1.0)

    def test_clamps_below_zero(self, catcher):
        catcher.set_energy(-0.5)
        assert catcher.energy == pytest.approx(0.0)
