# tests/test_resolver.py
import pytest

from tests.utils import FakeRNG
from tests.utils import fake_game, fake_game_with_batter_cycle
from src.game.resolver import Resolver
from src.game.events.out import OutRecordedEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.intents.pitch import PitchIntent
from src.game.events.plate_appearance import PlateAppearanceEndEvent

@pytest.fixture
def pitch_intent():
    return PitchIntent(
        pitcher_id="p1",
        batter_id="b1",
    )

@pytest.fixture
def resolver():
    return Resolver(rng=FakeRNG([1, 1, 1, 1]))


def test_resolver_returns_events(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())

    assert len(events) >= 1


def test_one_pitch_thrown_event(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())

    pitches = [e for e in events if isinstance(e, PitchThrownEvent)]
    assert len(pitches) == 1

def test_pitch_intent_emits_exactly_one_pitch_thrown_event(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())

    pitches = [e for e in events if isinstance(e, PitchThrownEvent)]
    assert len(pitches) == 1


def test_pitch_thrown_event_captures_count_snapshot(resolver, pitch_intent):
    game = fake_game()
    game.count.balls = 2
    game.count.strikes = 1

    events = resolver.resolve(pitch_intent, game)

    pitch = next(e for e in events if isinstance(e, PitchThrownEvent))
    assert pitch.count.balls == 2
    assert pitch.count.strikes == 1

def test_pitch_can_result_in_ball(resolver, pitch_intent):
    resolver.rng = FakeRNG([0.1])  # whatever threshold you defined

    events = resolver.resolve(pitch_intent, fake_game())

    assert any(e.__class__.__name__ == "BallEvent" for e in events)


def test_one_pitch_thrown_event(resolver, pitch_intent):
    # resolver = Resolver(rng=FakeRNG([1, 1, 1, 1]))
    events = resolver.resolve(pitch_intent, fake_game())

    pitches = [e for e in events if isinstance(e, PitchThrownEvent)]
    assert len(pitches) == 1

def test_plate_appearance_ends_once(resolver, pitch_intent):
    """
    The resolver may emit at most ONE PlateAppearanceEndEvent.
    The reason must be the most specific terminal result.
    """
    events = resolver.resolve(pitch_intent, fake_game())

    pa_end = [e for e in events if isinstance(e, PlateAppearanceEndEvent)]
    assert len(pa_end) <= 1

def test_out_does_not_end_pa_by_itself():
    game = fake_game_with_batter_cycle()
    out = OutRecordedEvent("out")
    out.apply(game)
    assert not game._plate_appearance_over()

def test_pa_end_advances_batter():
    game = fake_game_with_batter_cycle()
    old_batter = game.current_batter
    pae = PlateAppearanceEndEvent("walk")
    pae.apply(game)
    game._post_event()
    assert game.current_batter is not old_batter



# # Layer 2
# def test_pitch_thrown_is_first_event():
#     events = resolver.resolve(intent, fake_game())
#     assert isinstance(events[0], PitchThrownEvent)

# def test_pa_end_is_last_if_present():
#     events = resolver.resolve(intent, fake_game())
#     pa_end = [e for e in events if isinstance(e, PlateAppearanceEndEvent)]

#     if pa_end:
#         assert events[-1] is pa_end[0]

# # layer 3

# def test_walk_events():
#     rng = FakeRNG(outcome="ball", balls=4)
#     events = resolver.resolve(intent, fake_game(count="3-0"))

#     assert_event_types(
#         events,
#         [
#             PitchThrownEvent,
#             BallEvent,
#             RunnerAdvancedEvent,
#             PlateAppearanceEndEvent,
#         ],
#     )

# def test_strikeout_events():
#     rng = FakeRNG(outcome="strike", strikes=3)
#     events = resolver.resolve(intent, fake_game(count="0-2"))

#     assert_event_types(
#         events,
#         [
#             PitchThrownEvent,
#             StrikeEvent,
#             PlateAppearanceEndEvent,
#             OutRecordedEvent,
#         ],
#     )

# # layer 4

# def test_game_does_not_generate_events():
#     game = Game(...)
#     game.step()

#     assert game._queue_was_empty_before_step

# def test_one_step_advances_batter_once():
#     game.step()
#     assert game.lineup.position == 1

# def assert_event_types(events, types):
#     assert [type(e) for e in events] == types

