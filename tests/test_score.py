# tests/test_score.py
import pytest
from src.game.score import Score


class TestScoreInitialization:
    """Test initial state of Score."""

    def test_score_starts_at_zero_zero(self):
        score = Score()
        assert score.home == 0
        assert score.away == 0

    def test_inning_lists_start_empty(self):
        score = Score()
        assert score.away_innings == []
        assert score.home_innings == []

    def test_str_representation_initial(self):
        score = Score()
        s = str(score)
        assert "Home:" in s
        assert "Visitor:" in s
        assert "0" in s


class TestEnsureInning:
    """Test ensuring innings exist."""

    def test_ensure_first_inning(self):
        score = Score()
        score.ensure_inning(1)
        assert len(score.away_innings) == 1
        assert len(score.home_innings) == 1
        assert score.away_innings[0] == 0
        assert score.home_innings[0] == 0

    def test_ensure_multiple_innings(self):
        score = Score()
        score.ensure_inning(5)
        assert len(score.away_innings) == 5
        assert len(score.home_innings) == 5
        assert all(runs == 0 for runs in score.away_innings)
        assert all(runs == 0 for runs in score.home_innings)

    def test_ensure_inning_is_idempotent(self):
        score = Score()
        score.ensure_inning(3)
        score.ensure_inning(3)
        assert len(score.away_innings) == 3
        assert len(score.home_innings) == 3

    def test_ensure_lower_inning_after_higher(self):
        score = Score()
        score.ensure_inning(9)
        score.ensure_inning(5)
        assert len(score.away_innings) == 9
        assert len(score.home_innings) == 9

    def test_ensure_inning_preserves_existing_runs(self):
        score = Score()
        score.away_innings = [1, 2, 3]
        score.home_innings = [0, 1, 0]
        score.ensure_inning(5)
        assert score.away_innings[:3] == [1, 2, 3]
        assert score.home_innings[:3] == [0, 1, 0]
        assert score.away_innings[3:] == [0, 0]
        assert score.home_innings[3:] == [0, 0]


class TestScoreRun:
    """Test scoring runs."""

    def test_score_away_run_first_inning(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        assert score.away == 1
        assert score.home == 0
        assert score.away_innings[0] == 1

    def test_score_home_run_first_inning(self):
        score = Score()
        score.score_run(top=False, inning_number=1)
        assert score.home == 1
        assert score.away == 0
        assert score.home_innings[0] == 1

    def test_score_multiple_runs_same_inning_away(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        assert score.away == 3
        assert score.away_innings[0] == 3

    def test_score_multiple_runs_same_inning_home(self):
        score = Score()
        score.score_run(top=False, inning_number=1)
        score.score_run(top=False, inning_number=1)
        assert score.home == 2
        assert score.home_innings[0] == 2

    def test_score_runs_different_innings(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=3)
        score.score_run(top=True, inning_number=5)
        assert score.away == 3
        assert score.away_innings == [1, 0, 1, 0, 1]

    def test_score_run_automatically_ensures_inning(self):
        score = Score()
        score.score_run(top=True, inning_number=7)
        assert len(score.away_innings) == 7
        assert len(score.home_innings) == 7
        assert score.away_innings[6] == 1

    def test_score_both_teams_same_inning(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        assert score.away == 2
        assert score.home == 1
        assert score.away_innings[0] == 2
        assert score.home_innings[0] == 1

    def test_score_run_in_extras(self):
        score = Score()
        score.score_run(top=True, inning_number=10)
        score.score_run(top=False, inning_number=10)
        assert len(score.away_innings) == 10
        assert score.away_innings[9] == 1
        assert score.home_innings[9] == 1


class TestScoreProperties:
    """Test computed properties."""

    def test_away_property_sums_innings(self):
        score = Score()
        score.away_innings = [1, 2, 3, 0, 1]
        assert score.away == 7

    def test_home_property_sums_innings(self):
        score = Score()
        score.home_innings = [0, 0, 5, 1, 2]
        assert score.home == 8

    def test_properties_return_zero_for_empty(self):
        score = Score()
        assert score.away == 0
        assert score.home == 0

    def test_properties_update_when_innings_change(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        assert score.away == 1
        score.score_run(top=True, inning_number=2)
        assert score.away == 2


class TestStringRepresentation:
    """Test string formatting."""

    def test_str_zero_zero(self):
        score = Score()
        s = str(score)
        assert "Home:    0" in s
        assert "Visitor: 0" in s

    def test_str_with_runs(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        s = str(score)
        assert "Home:    1" in s
        assert "Visitor: 2" in s

    def test_str_contains_newlines(self):
        score = Score()
        s = str(score)
        assert s.count("\n") >= 2

    def test_str_high_score(self):
        score = Score()
        score.away_innings = [5, 0, 3, 2, 0, 0, 1, 0, 4]
        score.home_innings = [2, 1, 0, 0, 3, 1, 0, 2, 0]
        s = str(score)
        assert "Home:    9" in s
        assert "Visitor: 15" in s


class TestGameScenarios:
    """Test realistic game scenarios."""

    def test_shutout(self):
        """Home team shuts out visitors."""
        score = Score()
        for inning in [1, 3, 5, 7]:
            score.score_run(top=False, inning_number=inning)
        assert score.home == 4
        assert score.away == 0

    def test_close_game(self):
        """Tight 3-2 game."""
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=5)
        score.score_run(top=False, inning_number=3)
        score.score_run(top=False, inning_number=7)
        score.score_run(top=False, inning_number=9)
        assert score.away == 2
        assert score.home == 3

    def test_blowout(self):
        """One team scores many runs."""
        score = Score()
        # Away team scores 10 in first inning
        for _ in range(10):
            score.score_run(top=True, inning_number=1)
        assert score.away == 10
        assert score.away_innings[0] == 10

    def test_back_and_forth(self):
        """Lead changes multiple times."""
        score = Score()
        # Away takes lead
        score.score_run(top=True, inning_number=1)
        assert score.away > score.home

        # Home ties and takes lead
        score.score_run(top=False, inning_number=2)
        score.score_run(top=False, inning_number=2)
        assert score.home > score.away

        # Away ties it
        score.score_run(top=True, inning_number=3)
        assert score.home == score.away

    def test_walk_off_scenario(self):
        """Home team scores winning run in bottom 9th."""
        score = Score()
        # Away scores 3 in top 9th
        for _ in range(3):
            score.score_run(top=True, inning_number=9)
        # Home already had 2
        score.home_innings = [1, 0, 0, 0, 1, 0, 0, 0, 0]
        score.ensure_inning(9)

        # Home scores 2 to win in bottom 9th
        score.score_run(top=False, inning_number=9)
        score.score_run(top=False, inning_number=9)

        assert score.home == 4
        assert score.away == 3

    def test_extra_innings_marathon(self):
        """Game goes to 15 innings."""
        score = Score()
        # Score tied through 9
        for inning in range(1, 10):
            score.score_run(top=True, inning_number=inning)
            score.score_run(top=False, inning_number=inning)

        # Home wins in 15th
        score.score_run(top=False, inning_number=15)

        assert len(score.home_innings) == 15
        assert score.home == 10
        assert score.away == 9

    def test_perfect_game_score(self):
        """Perfect game: 1-0 shutout."""
        score = Score()
        score.score_run(top=False, inning_number=5)
        assert score.home == 1
        assert score.away == 0

    def test_nine_inning_game_both_teams_score(self):
        """Normal 9-inning game."""
        score = Score()
        # Simulate scoring in various innings
        innings_data = [
            (1, True, 2),  # Away: 2 in 1st
            (1, False, 0),  # Home: 0 in 1st
            (3, True, 1),  # Away: 1 in 3rd
            (3, False, 3),  # Home: 3 in 3rd
            (5, True, 0),  # Away: 0 in 5th
            (5, False, 1),  # Home: 1 in 5th
            (8, True, 2),  # Away: 2 in 8th
            (8, False, 0),  # Home: 0 in 8th
        ]

        for inning, is_top, runs in innings_data:
            for _ in range(runs):
                score.score_run(top=is_top, inning_number=inning)

        assert score.away == 5
        assert score.home == 4


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_direct_list_modification(self):
        """Test that lists can be directly modified."""
        score = Score()
        score.away_innings = [1, 2, 3]
        score.home_innings = [0, 1, 0]
        assert score.away == 6
        assert score.home == 1

    def test_negative_runs_via_direct_modification(self):
        """Current implementation allows negative runs."""
        score = Score()
        score.away_innings = [-5, 3]
        assert score.away == -2
        # This is probably undesired behavior

    def test_zero_inning_number(self):
        """Current implementation allows inning 0."""
        score = Score()
        with pytest.raises(ValueError):
            score.score_run(top=True, inning_number=0)
        # This should probably raise an error

    def test_negative_inning_number(self):
        """Current implementation allows negative inning numbers."""
        score = Score()
        score.ensure_inning(-1)
        # This should probably raise an error

    def test_very_high_inning_number(self):
        """Test with inning 100."""
        score = Score()
        score.score_run(top=True, inning_number=100)
        assert len(score.away_innings) == 100
        assert score.away == 1

    def test_empty_string_in_list(self):
        """Lists can contain non-integers."""
        score = Score()
        score.away_innings = [1, "not a number", 3]
        # sum() will raise TypeError
        with pytest.raises(TypeError):
            _ = score.away

    def test_score_many_runs_single_inning(self):
        """Test scoring 20 runs in one inning."""
        score = Score()
        for _ in range(20):
            score.score_run(top=True, inning_number=1)
        assert score.away == 20
        assert score.away_innings[0] == 20

    def test_alternating_top_bottom_same_inning(self):
        """Score alternates between top and bottom of same inning."""
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        assert score.away == 2
        assert score.home == 2

    def test_score_out_of_order_innings(self):
        """Score runs in non-sequential innings."""
        score = Score()
        score.score_run(top=True, inning_number=9)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=5)
        assert score.away == 3
        assert len(score.away_innings) == 9


class TestInningAccess:
    """Test accessing individual inning data."""

    def test_access_specific_inning_away(self):
        score = Score()
        score.away_innings = [1, 0, 3, 2]
        assert score.away_innings[0] == 1
        assert score.away_innings[2] == 3

    def test_access_specific_inning_home(self):
        score = Score()
        score.home_innings = [0, 2, 1, 0, 5]
        assert score.home_innings[1] == 2
        assert score.home_innings[4] == 5

    def test_modify_specific_inning(self):
        score = Score()
        score.away_innings = [1, 2, 3]
        score.away_innings[1] = 5
        assert score.away == 9  # 1 + 5 + 3


class TestScoreComparison:
    """Test comparing scores."""

    def test_home_leading(self):
        score = Score()
        score.score_run(top=False, inning_number=1)
        score.score_run(top=False, inning_number=1)
        score.score_run(top=True, inning_number=1)
        assert score.home > score.away

    def test_away_leading(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        assert score.away > score.home

    def test_tied(self):
        score = Score()
        score.score_run(top=True, inning_number=1)
        score.score_run(top=False, inning_number=1)
        assert score.home == score.away

    def test_tied_at_zero(self):
        score = Score()
        assert score.home == score.away == 0


class TestKeywordOnlyArguments:
    """Test that score_run requires keyword arguments."""

    def test_score_run_requires_keywords(self):
        score = Score()
        # This should work
        score.score_run(top=True, inning_number=1)

        # This should fail (positional arguments not allowed due to *)
        with pytest.raises(TypeError):
            score.score_run(True, 1)

    def test_score_run_with_swapped_keywords(self):
        """Keywords can be in any order."""
        score = Score()
        score.score_run(inning_number=5, top=False)
        assert score.home == 1
        assert score.home_innings[4] == 1
