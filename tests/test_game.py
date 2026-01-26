# tests/test_game.py
import pytest
import logging
import random
from unittest.mock import Mock

from src.game.game import Game, GameStateError, GameResult, GameContext
from src.game.event import GameEvent
from src.game.intent import GameIntent


class TestGameInitialization:
    """Test Game initialization."""

    def test_init_with_valid_teams(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        assert game.home == home
        assert game.away == away
        assert game.bat_team == away  # Away bats first
        assert game.pitch_team == home

    def test_init_creates_game_state(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        assert game.inning is not None
        assert game.count is not None
        assert game.bases is not None
        assert game.score is not None

    def test_init_with_custom_rng(self, mock_teams):
        home, away = mock_teams
        rng = random.Random(42)
        game = Game(home, away, rng=rng)

        assert game.rng is rng

    def test_init_validates_none_teams(self):
        with pytest.raises(ValueError, match="Both home and away teams are required"):
            Game(None, None)

    def test_init_validates_none_home(self):
        away = Mock()
        with pytest.raises(ValueError, match="Both home and away teams are required"):
            Game(None, away)

    # def test_init_validates_same_team(self, mock_teams):
    #     home, _ = mock_teams
    #     home.id = "same-id"
    #     away = Mock()
    #     away.id = "same-id"

    #     with pytest.raises(ValueError, match="cannot be the same"):
    #         Game(home, away)

    def test_init_default_values(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        assert game.current_batter is None
        assert game.current_pitcher is None
        assert game._plate_appearance_complete is False
        assert game._pa_end_reason is None
        assert game.pauses is False


class TestGameContext:
    """Test GameContext snapshots."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_get_context_initial_state(self, game):
        # Set up mock players
        game.current_batter = Mock()
        game.current_batter.player.name = "Batter One"
        game.current_pitcher = Mock()
        game.current_pitcher.name = "Pitcher One"

        context = game.get_context()

        assert isinstance(context, GameContext)
        assert context.inning_number == 1
        assert context.inning_top is True
        assert context.balls == 0
        assert context.strikes == 0
        assert context.outs == 0
        assert context.home_score == 0
        assert context.away_score == 0

    def test_get_context_is_immutable(self, game):
        game.current_batter = Mock()
        game.current_batter.player.name = "Batter"
        game.current_pitcher = Mock()
        game.current_pitcher.name = "Pitcher"

        context = game.get_context()

        with pytest.raises(Exception):  # FrozenInstanceError
            context.balls = 5

    def test_context_str_representation(self, game):
        game.current_batter = Mock()
        game.current_batter.player.name = "Batter"
        game.current_pitcher = Mock()
        game.current_pitcher.name = "Pitcher"

        context = game.get_context()
        s = str(context)

        assert "Top 1" in s
        assert "0-0" in s  # Score
        assert "0 out" in s


class TestGameResult:
    """Test GameResult."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_get_result_raises_if_not_over(self, game):
        with pytest.raises(RuntimeError, match="not over"):
            game.get_result()

    def test_get_result_home_wins(self, game):
        # Set up winning scenario
        game.inning.number = 9
        game.inning.top = False
        game.score._home_innings = [0, 0, 0, 0, 0, 0, 0, 0, 5]
        game.score._away_innings = [0, 0, 0, 0, 0, 0, 0, 0, 3]

        result = game.get_result()

        assert isinstance(result, GameResult)
        assert result.home_team == "Team"
        assert result.away_team == "Team"
        assert result.home_score == 5
        assert result.away_score == 3
        assert result.winner == "Team"
        assert result.winning_margin == 2
        assert result.innings_played == 9

    def test_get_result_away_wins(self, game):
        game.inning.number = 9
        game.inning.top = False
        game.score._home_innings = [0, 0, 0, 0, 0, 0, 0, 0, 2]
        game.score._away_innings = [0, 0, 0, 0, 0, 0, 0, 0, 7]

        # Make game over (away leading after 9)
        game.inning.outs = 3

        result = game.get_result()

        assert result.winner == "Team"
        assert result.winning_margin == 5

    def test_result_str_representation(self, game):
        game.inning.number = 9
        game.inning.top = False
        game.score._home_innings = [0, 0, 0, 0, 0, 0, 0, 0, 5]
        game.score._away_innings = [0, 0, 0, 0, 0, 0, 0, 0, 3]

        result = game.get_result()
        s = str(result)

        assert "Team" in s
        assert "5" in s
        assert "3" in s


class TestIsOver:
    """Test game completion logic."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_is_over_first_inning(self, game):
        assert game.is_over() is False

    def test_is_over_before_ninth(self, game):
        game.inning.number = 5
        assert game.is_over() is False

    def test_is_over_top_ninth_tied(self, game):
        game.inning.number = 9
        game.inning.top = True
        game.score._home_innings = [1] * 9
        game.score._away_innings = [1] * 9

        assert game.is_over() is False

    def test_is_over_bottom_ninth_home_winning(self, game):
        game.inning.number = 9
        game.inning.top = False
        game.score._home_innings = [5]
        game.score._away_innings = [3]

        assert game.is_over() is True

    def test_is_over_bottom_ninth_home_losing(self, game):
        game.inning.number = 9
        game.inning.top = False
        game.score._home_innings = [3]
        game.score._away_innings = [5]

        assert game.is_over() is False

    def test_is_over_extra_innings_bottom_home_winning(self, game):
        game.inning.number = 12
        game.inning.top = False
        game.score._home_innings = [0] * 11 + [1]
        game.score._away_innings = [0] * 12

        assert game.is_over() is True

    def test_is_over_extra_innings_tied(self, game):
        game.inning.number = 11
        game.inning.top = True
        game.score._home_innings = [1] * 10
        game.score._away_innings = [1] * 10

        assert game.is_over() is False

    def test_is_over_extra_innings_complete_not_tied(self, game):
        game.inning.number = 10
        game.inning.top = False  # Bottom of 10th
        game.inning.outs = 3
        game.score._home_innings = [0] * 9 + [0]
        game.score._away_innings = [0] * 9 + [1]

        # After bottom 10th is played
        assert game.is_over() is True


class TestTeamSwapping:
    """Test team swapping between innings."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_initial_team_setup(self, game):
        assert game.bat_team == game.away
        assert game.pitch_team == game.home

    def test_swap_teams(self, game):
        game._swap_teams()

        assert game.bat_team == game.home
        assert game.pitch_team == game.away

    def test_swap_teams_twice(self, game):
        game._swap_teams()
        game._swap_teams()

        assert game.bat_team == game.away
        assert game.pitch_team == game.home


class TestEventQueue:
    """Test event queue management."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    @pytest.fixture
    def mock_event(self):
        event = Mock(spec=GameEvent)
        event.label.return_value = "MockEvent"
        event.apply.return_value = []
        return event

    def test_enqueue_adds_to_back(self, game, mock_event):
        event1 = Mock(spec=GameEvent)
        event2 = Mock(spec=GameEvent)

        game._enqueue([event1, event2])

        assert len(game._queue) == 2
        assert game._queue[0] == event1
        assert game._queue[1] == event2

    def test_enqueue_empty_list_raises(self, game):
        with pytest.raises(RuntimeError, match="Cannot enqueue empty"):
            game._enqueue([])

    def test_dequeue_removes_from_front(self, game, mock_event):
        event1 = Mock(spec=GameEvent)
        event2 = Mock(spec=GameEvent)
        game._queue.extend([event1, event2])

        result = game._dequeue()

        assert result == event1
        assert len(game._queue) == 1

    def test_enqueue_left_single_event(self, game, mock_event):
        event1 = Mock(spec=GameEvent)
        event2 = Mock(spec=GameEvent)
        game._queue.append(event1)

        game._enqueue_left(event2)

        assert game._queue[0] == event2
        assert game._queue[1] == event1

    def test_enqueue_left_list_preserves_order(self, game):
        event1 = Mock(spec=GameEvent)
        event2 = Mock(spec=GameEvent)
        event3 = Mock(spec=GameEvent)

        game._queue.append(event1)
        game._enqueue_left([event2, event3])

        # event2, event3 should be before event1
        assert game._queue[0] == event2
        assert game._queue[1] == event3
        assert game._queue[2] == event1

    def test_enqueue_left_empty_list_does_nothing(self, game):
        game._enqueue_left([])
        assert len(game._queue) == 0


class TestPlateAppearance:
    """Test plate appearance tracking."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_mark_plate_appearance_complete(self, game):
        game._mark_plate_appearance_complete("strikeout")

        assert game._plate_appearance_complete is True
        assert game._pa_end_reason == "strikeout"

    def test_advance_batter_resets_pa_state(self, game):
        game._plate_appearance_complete = True
        game._pa_end_reason = "walk"

        # Mock next batter
        mock_batter = Mock()
        mock_batter.player.name = "Next Batter"
        game.bat_team.next_batter = Mock(return_value=mock_batter)

        game._advance_batter()

        assert game._plate_appearance_complete is False
        assert game._pa_end_reason is None


class TestEndHalfInning:
    """Test half-inning transitions."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        # Mock sync_players
        mock_batter = Mock()
        mock_batter.player.name = "Batter"
        mock_pitcher = Mock()
        mock_pitcher.name = "Pitcher"

        game.bat_team.current_batter = mock_batter
        game.pitch_team.current_pitcher = mock_pitcher

        return game

    def test_end_half_inning_increments_inning(self, game):
        game._end_half_inning()

        assert game.inning.number == 1
        assert game.inning.top is False  # Now bottom

    def test_end_half_inning_clears_bases(self, game):
        game.bases.advance("r1", None, 1)
        game.bases.advance("r2", None, 2)

        game._end_half_inning()

        assert game.bases.runner_on(1) is None
        assert game.bases.runner_on(2) is None

    def test_end_half_inning_resets_count(self, game):
        game.count.balls = 3
        game.count.strikes = 2

        game._end_half_inning()

        assert game.count.balls == 0
        assert game.count.strikes == 0

    # def test_end_half_inning_clears_queue(self, game):
    #     event = Mock(spec=GameEvent)
    #     game._queue.append(event)

    #     game._end_half_inning()

    #     assert len(game._queue) == 0

    def test_end_half_inning_swaps_teams(self, game):
        original_bat_team = game.bat_team
        original_pitch_team = game.pitch_team

        game._end_half_inning()

        assert game.bat_team == original_pitch_team
        assert game.pitch_team == original_bat_team


class TestPostEvent:
    """Test post-event housekeeping."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        # Mock next batter
        mock_batter = Mock()
        mock_batter.player.name = "Next Batter"
        game.bat_team.next_batter = Mock(return_value=mock_batter)

        return game

    def test_post_event_advances_batter_when_pa_complete(self, game):
        game._plate_appearance_complete = True

        game._post_event()

        assert game._plate_appearance_complete is False
        assert game.count.balls == 0
        assert game.count.strikes == 0

    def test_post_event_ends_inning_when_three_outs(self, game):
        game.inning.outs = 3

        # Mock sync_players
        mock_batter = Mock()
        mock_batter.player.name = "Batter"
        mock_pitcher = Mock()
        mock_pitcher.name = "Pitcher"

        game.bat_team.current_batter = mock_batter
        game.pitch_team.current_pitcher = mock_pitcher

        game._post_event()

        # Should be in bottom of 1st now
        assert game.inning.number == 1
        assert game.inning.top is False
        assert game.inning.outs == 0

    def test_post_event_raises_if_pa_complete_with_queue(self, game):
        game._plate_appearance_complete = True
        event = Mock(spec=GameEvent)
        event.label.return_value = "MockEvent"
        game._queue.append(event)

        with pytest.raises(GameStateError, match="PlateAppearanceEndEvent fired with"):
            game._post_event()


class TestHalfInningOver:
    """Test half-inning completion check."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_half_inning_not_over_zero_outs(self, game):
        assert game._half_inning_over() is False

    def test_half_inning_not_over_one_out(self, game):
        game.inning.outs = 1
        assert game._half_inning_over() is False

    def test_half_inning_not_over_two_outs(self, game):
        game.inning.outs = 2
        assert game._half_inning_over() is False

    def test_half_inning_over_three_outs(self, game):
        game.inning.outs = 3
        assert game._half_inning_over() is True


class TestPauseResume:
    """Test pause/resume functionality."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_initial_pause_state(self, game):
        assert game.pauses is False

    def test_pause(self, game):
        game.pause()
        assert game.pauses is True

    def test_resume(self, game):
        game.pause()
        game.resume()
        assert game.pauses is False

    def test_toggle_pause_from_unpaused(self, game):
        game.toggle_pause()
        assert game.pauses is True

    def test_toggle_pause_from_paused(self, game):
        game.pause()
        game.toggle_pause()
        assert game.pauses is False


class TestProperties:
    """Test game properties."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        return Game(home, away)

    def test_batting_team_name(self, game):
        assert game.batting_team_name == "Away Team"

    def test_pitching_team_name(self, game):
        assert game.pitching_team_name == "Home Team"

    def test_inning_state(self, game):
        state = game.inning_state
        assert "Top" in state
        assert "1" in state

    def test_game_state_summary(self, game):
        summary = game.game_state_summary
        assert "Team" in summary
        assert "0 out" in summary


class TestStep:
    """Test step execution."""

    @pytest.fixture
    def game(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        # Mock components
        game.intent_generator = Mock()
        game.resolver = Mock()

        # Mock next batter
        mock_batter = Mock()
        mock_batter.player.name = "Batter"
        game.bat_team.next_batter = Mock(return_value=mock_batter)

        return game

    def test_step_with_empty_queue_generates_intent(self, game):
        mock_intent = Mock(spec=GameIntent)
        mock_event = Mock(spec=GameEvent)
        mock_event.label.return_value = "MockEvent"
        mock_event.apply.return_value = []

        game.intent_generator.next_intent.return_value = mock_intent
        game.resolver.resolve.return_value = [mock_event]

        game.step()

        game.intent_generator.next_intent.assert_called_once()
        game.resolver.resolve.assert_called_once_with(mock_intent, game)

    def test_step_with_queued_event_applies_it(self, game):
        mock_event = Mock(spec=GameEvent)
        mock_event.label.return_value = "MockEvent"
        mock_event.apply.return_value = []
        mock_event.log_level.return_value = logging.INFO
        mock_event.describe.return_value = "Mock event description"

        game._queue.append(mock_event)

        game.step()

    def test_step_with_followups_prepends_them(self, game):
        event1 = Mock(spec=GameEvent)
        event1.label.return_value = "Event1"

        followup1 = Mock(spec=GameEvent)
        followup1.label.return_value = "Followup1"
        followup1.apply.return_value = []
        event1.log_level.return_value = logging.INFO
        event1.describe.return_value = "Mock event description"

        followup2 = Mock(spec=GameEvent)
        followup2.label.return_value = "Followup2"

        event1.apply.return_value = [followup1, followup2]

        game._queue.append(event1)
        game.step()

        # Followups should be at front
        assert game._queue[0] == followup1
        assert game._queue[1] == followup2


class TestIntegration:
    """Integration tests."""

    @pytest.fixture
    def mock_teams(self):
        home = Mock()
        home.id = "home"
        home.name = "Home"
        home.has_lineup = True
        home.players = []

        away = Mock()
        away.id = "away"
        away.name = "Away"
        away.has_lineup = True
        away.players = []

        return home, away

    def test_full_inning_transition(self, mock_teams):
        home, away = mock_teams
        game = Game(home, away)

        # Mock sync_players
        mock_batter = Mock()
        mock_batter.player.name = "Batter"
        mock_pitcher = Mock()
        mock_pitcher.name = "Pitcher"

        home.current_batter = mock_batter
        away.current_batter = mock_batter
        home.current_pitcher = mock_pitcher
        away.current_pitcher = mock_pitcher

        # Top of 1st
        assert game.inning.number == 1
        assert game.inning.top is True
        assert game.bat_team == away

        # Simulate 3 outs
        game.inning.outs = 3
        game._end_half_inning()

        # Bottom of 1st
        assert game.inning.number == 1
        assert game.inning.top is False
        assert game.bat_team == home

        # Simulate 3 more outs
        game.inning.outs = 3
        game._end_half_inning()

        # Top of 2nd
        assert game.inning.number == 2
        assert game.inning.top is True
        assert game.bat_team == away
