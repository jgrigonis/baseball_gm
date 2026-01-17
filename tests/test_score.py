# tests/test_score.py
import pytest
from src.game.score import Score, ScoreSnapshot


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
    
    def test_repr_initial(self):
        score = Score()
        assert repr(score) == "Score(home=0, away=0)"
    
    def test_initial_leader(self):
        score = Score()
        assert score.leader == "tied"
        assert score.is_tied is True
    
    def test_initial_differential(self):
        score = Score()
        assert score.differential == 0


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
        score.score_run(top=True, inning_number=1, runs=1)
        score.score_run(top=True, inning_number=2, runs=2)
        score.score_run(top=True, inning_number=3, runs=3)
        score.score_run(top=False, inning_number=2, runs=1)
        
        score.ensure_inning(5)
        assert score.away_innings[:3] == [1, 2, 3]
        assert score.home_innings[:3] == [0, 1, 0]
        assert score.away_innings[3:] == [0, 0]
        assert score.home_innings[3:] == [0, 0]
    
    def test_ensure_inning_validates_negative(self):
        score = Score()
        with pytest.raises(ValueError, match="Inning number must be at least 1"):
            score.ensure_inning(-1)
    
    def test_ensure_inning_validates_zero(self):
        score = Score()
        with pytest.raises(ValueError, match="Inning number must be at least 1"):
            score.ensure_inning(0)
    
    def test_ensure_inning_validates_type(self):
        score = Score()
        with pytest.raises(TypeError, match="Inning number must be an integer"):
            score.ensure_inning(3.5)


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
    
    def test_score_multiple_runs_at_once(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        assert score.away == 5
        assert score.away_innings[0] == 5
    
    def test_score_zero_runs_does_nothing(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=0)
        assert score.away == 0
        assert score.away_innings == []
    
    def test_score_run_validates_negative_runs(self):
        score = Score()
        with pytest.raises(ValueError, match="Cannot score negative runs"):
            score.score_run(top=True, inning_number=1, runs=-5)
    
    def test_score_run_validates_negative_inning(self):
        score = Score()
        with pytest.raises(ValueError, match="Inning number must be at least 1"):
            score.score_run(top=True, inning_number=-1)
    
    def test_score_run_validates_zero_inning(self):
        score = Score()
        with pytest.raises(ValueError, match="Inning number must be at least 1"):
            score.score_run(top=True, inning_number=0)
    
    def test_score_run_validates_inning_type(self):
        score = Score()
        with pytest.raises(TypeError, match="Inning number must be an integer"):
            score.score_run(top=True, inning_number=3.5)


class TestScoreProperties:
    """Test computed properties."""
    
    def test_away_property_sums_innings(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=1)
        score.score_run(top=True, inning_number=2, runs=2)
        score.score_run(top=True, inning_number=3, runs=3)
        score.score_run(top=True, inning_number=5, runs=1)
        assert score.away == 7
    
    def test_home_property_sums_innings(self):
        score = Score()
        score.score_run(top=False, inning_number=3, runs=5)
        score.score_run(top=False, inning_number=4, runs=1)
        score.score_run(top=False, inning_number=5, runs=2)
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
    
    def test_away_innings_returns_copy(self):
        """Verify that away_innings returns a copy, not the original list."""
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        innings_copy = score.away_innings
        innings_copy[0] = 999
        # Original should be unchanged
        assert score.away_innings[0] == 5
    
    def test_home_innings_returns_copy(self):
        """Verify that home_innings returns a copy, not the original list."""
        score = Score()
        score.score_run(top=False, inning_number=1, runs=3)
        innings_copy = score.home_innings
        innings_copy[0] = 999
        # Original should be unchanged
        assert score.home_innings[0] == 3
    
    def test_differential_home_leading(self):
        score = Score()
        score.score_run(top=False, inning_number=1, runs=5)
        score.score_run(top=True, inning_number=1, runs=2)
        assert score.differential == 3  # 5 - 2
    
    def test_differential_away_leading(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=7)
        score.score_run(top=False, inning_number=1, runs=3)
        assert score.differential == -4  # 3 - 7
    
    def test_differential_tied(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        score.score_run(top=False, inning_number=1, runs=5)
        assert score.differential == 0
    
    def test_leader_home(self):
        score = Score()
        score.score_run(top=False, inning_number=1, runs=3)
        score.score_run(top=True, inning_number=1, runs=1)
        assert score.leader == "home"
    
    def test_leader_away(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=4)
        score.score_run(top=False, inning_number=1, runs=2)
        assert score.leader == "away"
    
    def test_leader_tied(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=3)
        score.score_run(top=False, inning_number=1, runs=3)
        assert score.leader == "tied"
    
    def test_is_tied_true(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=2)
        score.score_run(top=False, inning_number=1, runs=2)
        assert score.is_tied is True
    
    def test_is_tied_false(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=1)
        assert score.is_tied is False


class TestRunsInInning:
    """Test querying runs in specific innings."""
    
    def test_runs_in_inning_away(self):
        score = Score()
        score.score_run(top=True, inning_number=3, runs=5)
        assert score.runs_in_inning(3, top=True) == 5
    
    def test_runs_in_inning_home(self):
        score = Score()
        score.score_run(top=False, inning_number=2, runs=3)
        assert score.runs_in_inning(2, top=False) == 3
    
    def test_runs_in_inning_not_yet_played(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=1)
        assert score.runs_in_inning(5, top=True) == 0
    
    def test_runs_in_inning_zero_runs_scored(self):
        score = Score()
        score.ensure_inning(5)
        assert score.runs_in_inning(3, top=True) == 0
    
    def test_runs_in_inning_validates_negative(self):
        score = Score()
        with pytest.raises(ValueError, match="Inning number must be at least 1"):
            score.runs_in_inning(-1, top=True)
    
    def test_runs_in_inning_validates_type(self):
        score = Score()
        with pytest.raises(TypeError, match="Inning number must be an integer"):
            score.runs_in_inning(3.5, top=True)


class TestSnapshot:
    """Test snapshot functionality."""
    
    def test_snapshot_empty_score(self):
        score = Score()
        snap = score.snapshot()
        assert isinstance(snap, ScoreSnapshot)
        assert snap.away_innings == ()
        assert snap.home_innings == ()
        assert snap.away_total == 0
        assert snap.home_total == 0
    
    def test_snapshot_with_runs(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=2)
        score.score_run(top=True, inning_number=3, runs=1)
        score.score_run(top=False, inning_number=2, runs=3)
        
        snap = score.snapshot()
        assert snap.away_innings == (2, 0, 1)
        assert snap.home_innings == (0, 3, 0)
        assert snap.away_total == 3
        assert snap.home_total == 3
    
    def test_snapshot_is_frozen(self):
        score = Score()
        snap = score.snapshot()
        with pytest.raises(Exception):  # FrozenInstanceError
            snap.away_total = 999
    
    def test_snapshot_is_independent(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        snap = score.snapshot()
        
        # Change score after snapshot
        score.score_run(top=True, inning_number=2, runs=10)
        
        # Snapshot should be unchanged
        assert snap.away_total == 5
        assert score.away == 15
    
    def test_multiple_snapshots(self):
        score = Score()
        snap1 = score.snapshot()
        
        score.score_run(top=True, inning_number=1, runs=1)
        snap2 = score.snapshot()
        
        score.score_run(top=False, inning_number=1, runs=2)
        snap3 = score.snapshot()
        
        assert snap1.away_total == 0 and snap1.home_total == 0
        assert snap2.away_total == 1 and snap2.home_total == 0
        assert snap3.away_total == 1 and snap3.home_total == 2


class TestClear:
    """Test clearing the score."""
    
    def test_clear_empty_score(self):
        score = Score()
        score.clear()
        assert score.away == 0
        assert score.home == 0
        assert score.away_innings == []
        assert score.home_innings == []
    
    def test_clear_with_runs(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        score.score_run(top=False, inning_number=2, runs=3)
        
        score.clear()
        
        assert score.away == 0
        assert score.home == 0
        assert score.away_innings == []
        assert score.home_innings == []
    
    def test_clear_then_score(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=10)
        score.clear()
        score.score_run(top=False, inning_number=1, runs=2)
        
        assert score.away == 0
        assert score.home == 2


class TestStringRepresentation:
    """Test string formatting."""
    
    def test_str_zero_zero(self):
        score = Score()
        s = str(score)
        assert "Home:    0" in s
        assert "Visitor: 0" in s
    
    def test_str_with_runs(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=2)
        score.score_run(top=False, inning_number=1, runs=1)
        s = str(score)
        assert "Home:    1" in s
        assert "Visitor: 2" in s
    
    def test_str_contains_newlines(self):
        score = Score()
        s = str(score)
        assert s.count("\n") >= 2
    
    def test_str_high_score(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=15)
        score.score_run(top=False, inning_number=1, runs=9)
        s = str(score)
        assert "Home:    9" in s
        assert "Visitor: 15" in s
    
    def test_repr(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=3)
        score.score_run(top=False, inning_number=1, runs=2)
        assert repr(score) == "Score(home=2, away=3)"


class TestScoreboard:
    """Test the scoreboard display."""
    
    def test_scoreboard_empty(self):
        score = Score()
        board = score.scoreboard()
        assert "Away|" in board
        assert "Home|" in board
        assert "R |" in board  # Runs column
    
    def test_scoreboard_with_runs(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=2)
        score.score_run(top=False, inning_number=1, runs=1)
        score.score_run(top=True, inning_number=3, runs=3)
        
        board = score.scoreboard()
        assert " 2 |" in board  # Away scored 2 in 1st
        assert " 1 |" in board  # Home scored 1 in 1st
        assert " 3 |" in board  # Away scored 3 in 3rd
        assert " 5 |" in board  # Away total
        assert "Home|" in board and "Away|" in board
    
    def test_scoreboard_displays_nine_innings_minimum(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=1)
        board = score.scoreboard()
        # Should show at least 9 innings
        for i in range(1, 10):
            assert f" {i} |" in board or f" {i:2} |" in board
    
    def test_scoreboard_extra_innings(self):
        score = Score()
        score.score_run(top=True, inning_number=12, runs=1)
        board = score.scoreboard()
        assert "12" in board
    
    def test_scoreboard_custom_max_innings(self):
        score = Score()
        score.score_run(top=True, inning_number=1, runs=1)
        board = score.scoreboard(max_innings=5)
        # Should only show 5 innings
        assert board.count("|") >= 5


class TestGameScenarios:
    """Test realistic game scenarios."""
    
    def test_shutout(self):
        """Home team shuts out visitors."""
        score = Score()
        for inning in [1, 3, 5, 7]:
            score.score_run(top=False, inning_number=inning)
        assert score.home == 4
        assert score.away == 0
        assert score.leader == "home"
    
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
        assert score.leader == "home"
        assert score.differential == 1
    
    def test_blowout(self):
        """One team scores many runs."""
        score = Score()
        score.score_run(top=True, inning_number=1, runs=10)
        assert score.away == 10
        assert score.away_innings[0] == 10
        assert score.leader == "away"
    
    def test_back_and_forth(self):
        """Lead changes multiple times."""
        score = Score()
        # Away takes lead
        score.score_run(top=True, inning_number=1)
        assert score.leader == "away"
        
        # Home ties and takes lead
        score.score_run(top=False, inning_number=2, runs=2)
        assert score.leader == "home"
        
        # Away ties it
        score.score_run(top=True, inning_number=3)
        assert score.leader == "tied"
        assert score.is_tied is True
    
    def test_walk_off_scenario(self):
        """Home team scores winning run in bottom 9th."""
        score = Score()
        # Build up score through 8 innings
        score.score_run(top=False, inning_number=1, runs=1)
        score.score_run(top=False, inning_number=5, runs=1)
        
        # Away scores 3 in top 9th
        score.score_run(top=True, inning_number=9, runs=3)
        assert score.leader == "away"
        
        # Home scores 2 to win in bottom 9th
        score.score_run(top=False, inning_number=9, runs=2)
        
        assert score.home == 4
        assert score.away == 3
        assert score.leader == "home"
    
    def test_extra_innings_marathon(self):
        """Game goes to 15 innings."""
        score = Score()
        # Score tied through 9
        for inning in range(1, 10):
            score.score_run(top=True, inning_number=inning)
            score.score_run(top=False, inning_number=inning)
        
        assert score.is_tied is True
        
        # Home wins in 15th
        score.score_run(top=False, inning_number=15)
        
        assert len(score.home_innings) == 15
        assert score.home == 10
        assert score.away == 9
        assert score.leader == "home"
    
    def test_perfect_game_score(self):
        """Perfect game: 1-0 shutout."""
        score = Score()
        score.score_run(top=False, inning_number=5)
        assert score.home == 1
        assert score.away == 0
        assert score.differential == 1
    
    def test_nine_inning_game_both_teams_score(self):
        """Normal 9-inning game."""
        score = Score()
        score.score_run(top=True, inning_number=1, runs=2)
        score.score_run(top=True, inning_number=3, runs=1)
        score.score_run(top=True, inning_number=8, runs=2)
        score.score_run(top=False, inning_number=3, runs=3)
        score.score_run(top=False, inning_number=5, runs=1)
        
        assert score.away == 5
        assert score.home == 4
        assert score.leader == "away"


class TestEncapsulation:
    """Test that internal state is properly protected."""
    
    def test_cannot_directly_set_away_innings(self):
        """away_innings property is read-only."""
        score = Score()
        with pytest.raises(AttributeError):
            score.away_innings = [1, 2, 3]
    
    def test_cannot_directly_set_home_innings(self):
        """home_innings property is read-only."""
        score = Score()
        with pytest.raises(AttributeError):
            score.home_innings = [1, 2, 3]
    
    def test_modifying_returned_list_doesnt_affect_score(self):
        """Modifying the list returned by property doesn't change internal state."""
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        
        innings = score.away_innings
        innings[0] = 999
        
        assert score.away == 5  # Unchanged
        assert score.away_innings[0] == 5  # Unchanged


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
        score.score_run(inning_number=5, top=False, runs=3)
        assert score.home == 3
        assert score.home_innings[4] == 3
    
    def test_runs_in_inning_requires_keyword(self):
        """runs_in_inning requires top as keyword."""
        score = Score()
        score.score_run(top=True, inning_number=1, runs=5)
        
        # This should work
        assert score.runs_in_inning(1, top=True) == 5
        
        # This should fail
        with pytest.raises(TypeError):
            score.runs_in_inning(1, True)
