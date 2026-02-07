# tests/test_resolver_helper.py
from src.game.resolver import Resolver
from src.game.events.ball import BallEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.events.hits import SingleEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.strike import (
    StrikeEvent,
)
from src.game.events.out import OutRecordedEvent, GroundOutEvent
from src.game.events.double_play import DoublePlayEvent


#

# ================================================================
# EXAMPLE USAGE AND TEST CASES
# ================================================================


def test_ball_in_play():
    """Test the _ball_in_play helper"""
    from unittest.mock import Mock

    resolver = Mock()
    resolver._ball_in_play = Resolver._ball_in_play.__get__(resolver)

    # Test 1: Ball in play (single)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=SingleEvent),
        Mock(spec=RunnerAdvancedEvent),
        Mock(spec=PlateAppearanceEndEvent),
    ]
    assert resolver._ball_in_play(events) == True

    # Test 2: Not in play (ball)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=BallEvent),
    ]
    assert resolver._ball_in_play(events) == False

    # Test 3: Not in play (strike)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=StrikeEvent),
    ]
    assert resolver._ball_in_play(events) == False

    # Test 4: Ball in play (out)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=GroundOutEvent),
        Mock(spec=OutRecordedEvent),
        Mock(spec=PlateAppearanceEndEvent),
    ]
    assert resolver._ball_in_play(events) == True

    # Test 5: Ball in play (double play)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=DoublePlayEvent),
        Mock(spec=OutRecordedEvent),
        Mock(spec=OutRecordedEvent),
        Mock(spec=PlateAppearanceEndEvent),
    ]
    assert resolver._ball_in_play(events) == True


def test_find_pa_end_index():
    """Test the _find_pa_end_index helper"""
    from unittest.mock import Mock

    resolver = Mock()
    resolver._find_pa_end_index = Resolver._find_pa_end_index.__get__(resolver)

    # Test 1: PA end event present
    pa_end = Mock(spec=PlateAppearanceEndEvent)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=StrikeEvent),
        pa_end,
    ]
    assert resolver._find_pa_end_index(events) == 2

    # Test 2: PA end event not present
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=BallEvent),
    ]
    assert resolver._find_pa_end_index(events) is None

    # Test 3: PA end in middle (shouldn't happen, but test it)
    events = [
        Mock(spec=PitchThrownEvent),
        Mock(spec=StrikeEvent),
        Mock(spec=PlateAppearanceEndEvent),
        Mock(spec=RunnerAdvancedEvent),  # This shouldn't be after PA end
    ]
    assert resolver._find_pa_end_index(events) == 2


def test_inning_ended():
    """Test the _inning_ended helper"""
    from unittest.mock import Mock

    resolver = Mock()
    resolver._inning_ended = Resolver._inning_ended.__get__(resolver)

    # Test 1: No outs yet, no outs in events
    game = Mock()
    game.inning.outs = 0
    events = [Mock(spec=PitchThrownEvent), Mock(spec=BallEvent)]
    assert resolver._inning_ended(events, game) == False

    # Test 2: 2 outs already, 1 out in events
    game.inning.outs = 2
    events = [Mock(spec=OutRecordedEvent)]
    assert resolver._inning_ended(events, game) == True

    # Test 3: 1 out already, 2 outs in events
    game.inning.outs = 1
    events = [
        Mock(spec=OutRecordedEvent),
        Mock(spec=OutRecordedEvent),
    ]
    assert resolver._inning_ended(events, game) == True

    # Test 4: Exactly 3 outs
    game.inning.outs = 3
    events = []
    assert resolver._inning_ended(events, game) == True


if __name__ == "__main__":
    # Run tests
    test_ball_in_play()
    test_find_pa_end_index()
    test_inning_ended()
    print("All tests passed!")
