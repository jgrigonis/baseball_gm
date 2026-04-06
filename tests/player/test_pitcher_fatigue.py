# tests/test_fatigue.py
import pytest

from src.player.fatigue import PitcherFatigue, FatigueLevel
from src.player.pitch_fatigue_constants import FASTBALL_DRAIN


class TestPitcherFatigueInitialization:
    """Test PitcherFatigue initialization."""

    def test_default_initialization(self):
        """Test default values."""
        fatigue = PitcherFatigue()

        assert fatigue.pitches_thrown == 0
        assert fatigue.batters_faced == 0
        assert fatigue.energy == 1.0
        assert fatigue.stamina == 50

    def test_custom_stamina(self):
        """Test initialization with custom stamina."""
        fatigue = PitcherFatigue(stamina=70)

        assert fatigue.stamina == 70
        assert fatigue.energy == 1.0

    def test_low_stamina_pitcher(self):
        """Test initialization with low stamina."""
        fatigue = PitcherFatigue(stamina=30)

        assert fatigue.stamina == 30


class TestFatigueLevel:
    """
    Test fatigue level determination.

    These tests rely on the thresholds in PitcherFatigue

    FRESH_THRESHOLD = 0.85
    GOOD_THRESHOLD = 0.65
    TIRED_THRESHOLD = 0.40
    EXHAUSTED_THRESHOLD = 0.01

    """

    def test_fresh_level(self):
        """Test FRESH fatigue level."""
        fatigue = PitcherFatigue(energy=1.0)
        assert fatigue.get_level() == FatigueLevel.FRESH

        fatigue = PitcherFatigue(energy=0.85)
        assert fatigue.get_level() == FatigueLevel.FRESH

    def test_good_level(self):
        """Test GOOD fatigue level."""
        fatigue = PitcherFatigue(energy=0.84)
        assert fatigue.get_level() == FatigueLevel.GOOD

        fatigue = PitcherFatigue(energy=0.65)
        assert fatigue.get_level() == FatigueLevel.GOOD

    def test_tired_level(self):
        """Test TIRED fatigue level."""
        fatigue = PitcherFatigue(energy=0.64)
        assert fatigue.get_level() == FatigueLevel.TIRED

        fatigue = PitcherFatigue(energy=0.40)
        assert fatigue.get_level() == FatigueLevel.TIRED

    def test_exhausted_level(self):
        """Test EXHAUSTED fatigue level."""
        fatigue = PitcherFatigue(energy=0.39)
        assert fatigue.get_level() == FatigueLevel.EXHAUSTED

        fatigue = PitcherFatigue(energy=0.0)
        assert fatigue.get_level() == FatigueLevel.ZERO


class TestAddPitch:
    """Test pitch tracking and energy drain."""

    def test_single_fastball(self):
        """Test adding a single fastball."""
        fatigue = PitcherFatigue(stamina=50)
        initial_energy = fatigue.energy

        fatigue.add_pitch("fastball")

        assert fatigue.pitches_thrown == 1
        assert fatigue.energy < initial_energy
        assert fatigue.energy == pytest.approx(0.992, abs=0.001)

    def test_multiple_fastballs(self):
        """Test multiple fastball pitches."""
        fatigue = PitcherFatigue(stamina=50)

        for _ in range(10):
            fatigue.add_pitch("fastball")

        assert fatigue.pitches_thrown == 10
        assert fatigue.energy == pytest.approx(0.92, abs=0.001)

    def test_high_stamina_drains_slower(self):
        """Test that high stamina pitchers drain energy slower."""
        high_stamina = PitcherFatigue(stamina=70)
        normal_stamina = PitcherFatigue(stamina=50)

        # Throw same number of pitches
        for _ in range(10):
            high_stamina.add_pitch("fastball")
            normal_stamina.add_pitch("fastball")

        # High stamina should have more energy remaining
        assert high_stamina.energy > normal_stamina.energy

        # Verify the math: drain = FASTBALL_DRAIN * (50/stamina)
        # High stamina: FASTBALL_DRAIN * (50/70) = 0.00714 per pitch
        # Normal: FASTBALL_DRAIN * (50/50) = FASTBALL_DRAIN per pitch
        assert high_stamina.energy == pytest.approx(
            1.0 - (FASTBALL_DRAIN * 50 / 70 * 10), abs=0.001
        )
        assert normal_stamina.energy == pytest.approx(
            1.0 - (FASTBALL_DRAIN * 10), abs=0.001
        )

    def test_low_stamina_drains_faster(self):
        """Test that low stamina pitchers drain energy faster."""
        low_stamina = PitcherFatigue(stamina=30)
        normal_stamina = PitcherFatigue(stamina=50)

        for _ in range(10):
            low_stamina.add_pitch("fastball")
            normal_stamina.add_pitch("fastball")

        # Low stamina should have less energy remaining
        assert low_stamina.energy < normal_stamina.energy

        # Low stamina: FASTBALL_DRAIN * (50/30) = 0.01333 per pitch
        assert low_stamina.energy == pytest.approx(
            1.0 - (FASTBALL_DRAIN * 50 / 30 * 10), abs=0.001
        )

    def test_energy_cannot_go_negative(self):
        """Test that energy bottoms out at 0.0."""
        fatigue = PitcherFatigue(stamina=50)

        # Throw 2000 pitches (way more than needed to drain)
        for _ in range(2000):
            fatigue.add_pitch("fastball")

        assert fatigue.energy == 0.0
        assert fatigue.pitches_thrown == 2000

    def test_unknown_pitch_type_uses_default(self):
        """Test that unknown pitch types use default drain rate."""
        fatigue = PitcherFatigue(stamina=50)

        fatigue.add_pitch("goofy")  # Not in drain_rates dict

        # Should use default of FASTBALL_DRAIN
        assert fatigue.energy == pytest.approx(0.992, abs=0.001)


class TestAddBatter:
    """
    Test batter tracking.

    Currently, we never use the add_batter function in the actual code.

    """

    def test_single_batter(self):
        """Test adding a single batter."""
        fatigue = PitcherFatigue()

        fatigue.add_batter()

        assert fatigue.batters_faced == 1

    def test_multiple_batters(self):
        """Test adding multiple batters."""
        fatigue = PitcherFatigue()

        for _ in range(27):  # Full game
            fatigue.add_batter()

        assert fatigue.batters_faced == 27

    def test_batters_dont_affect_energy(self):
        """Test that adding batters doesn't directly affect energy."""
        fatigue = PitcherFatigue()
        initial_energy = fatigue.energy

        fatigue.add_batter()

        assert fatigue.energy == initial_energy


class TestStatModifier:
    """Test performance modifier based on fatigue."""

    def test_fresh_modifier(self):
        """Test FRESH gives 1.05 bonus."""
        fatigue = PitcherFatigue(energy=1.0)

        assert fatigue.get_stat_modifier() == 1.05

    def test_good_modifier(self):
        """Test GOOD gives 1.0 (no change)."""
        fatigue = PitcherFatigue(energy=0.75)

        assert fatigue.get_stat_modifier() == 1.0

    def test_tired_modifier(self):
        """Test TIRED gives 0.90 penalty."""
        fatigue = PitcherFatigue(energy=0.50)

        assert fatigue.get_stat_modifier() == 0.90

    def test_exhausted_modifier(self):
        """Test EXHAUSTED gives 0.75 penalty."""
        fatigue = PitcherFatigue(energy=0.20)

        assert fatigue.get_stat_modifier() == 0.75


class TestRealisticGameScenarios:
    """Test realistic game scenarios."""

    def test_complete_game_average_pitcher(self):
        """Test average pitcher throwing a 125 pitch complete game."""
        fatigue = PitcherFatigue(stamina=50)

        # Average game: ~125 pitches, 27 batters
        for _ in range(125):
            fatigue.add_pitch("fastball")

        for _ in range(27):
            fatigue.add_batter()

        assert fatigue.pitches_thrown == 125
        assert fatigue.batters_faced == 27
        # After 125 pitches: 1.0 - (FASTBALL_DRAIN * 125) = 0.0
        assert fatigue.energy == 0.0
        assert fatigue.get_level() == FatigueLevel.ZERO

    def test_short_outing_relief_pitcher(self):
        """Test relief pitcher with short outing."""
        fatigue = PitcherFatigue(stamina=45)

        # 20 pitches, 5 batters
        for _ in range(20):
            fatigue.add_pitch("fastball")

        for _ in range(5):
            fatigue.add_batter()

        assert fatigue.pitches_thrown == 20
        # Energy should still be relatively high
        expected_energy = 1.0 - (FASTBALL_DRAIN * 50 / 45 * 20)
        assert fatigue.energy == pytest.approx(expected_energy, abs=0.001)
        assert fatigue.get_level() in [FatigueLevel.FRESH, FatigueLevel.GOOD]

    def test_workhorse_pitcher(self):
        """Test high-stamina pitcher going deep into game."""
        fatigue = PitcherFatigue(stamina=70)

        # 120 pitches (deep into game)
        for _ in range(120):
            fatigue.add_pitch("fastball")

        # High stamina should still have some energy
        expected_energy = 1.0 - (0.008 * 50 / 70 * 120)
        assert fatigue.energy == pytest.approx(expected_energy, abs=0.001)
        # Should still be above exhausted level with high stamina
        assert fatigue.energy > 0.0

    def test_progression_through_fatigue_levels(self):
        """Test progression from FRESH to EXHAUSTED."""
        fatigue = PitcherFatigue(stamina=50)

        # Start fresh
        assert fatigue.get_level() == FatigueLevel.FRESH

        # Throw pitches until good
        while fatigue.get_level() == FatigueLevel.FRESH:
            fatigue.add_pitch("fastball")
        assert fatigue.get_level() == FatigueLevel.GOOD

        # Continue until tired
        while fatigue.get_level() == FatigueLevel.GOOD:
            fatigue.add_pitch("fastball")
        assert fatigue.get_level() == FatigueLevel.TIRED

        # Continue until exhausted
        while fatigue.get_level() == FatigueLevel.TIRED:
            fatigue.add_pitch("fastball")
        assert fatigue.get_level() == FatigueLevel.EXHAUSTED


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_stamina(self):
        """Test that zero stamina raises ValueError."""
        with pytest.raises(ValueError, match="Stamina must be positive"):
            _ = PitcherFatigue(stamina=0)

    def test_negative_stamina(self):
        """Test that negative stamina raises ValueError."""
        with pytest.raises(ValueError, match="Stamina must be positive"):
            _ = PitcherFatigue(stamina=-50)

    def test_very_high_stamina(self):
        """Test with extremely high stamina."""
        fatigue = PitcherFatigue(stamina=100)

        # Should drain very slowly
        for _ in range(100):
            fatigue.add_pitch("fastball")

        # 100 pitches * 0.01 * (50/100) = 0.50 energy drained
        assert fatigue.energy == pytest.approx(0.60, abs=0.001)
        assert fatigue.get_level() == FatigueLevel.TIRED

    def test_pitcher_at_threshold_boundary(self):
        """Test behavior exactly at threshold boundaries."""
        # Exactly at FRESH/GOOD boundary
        fatigue = PitcherFatigue(energy=0.85)
        assert fatigue.get_level() == FatigueLevel.FRESH

        fatigue.energy = 0.8499999
        assert fatigue.get_level() == FatigueLevel.GOOD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
