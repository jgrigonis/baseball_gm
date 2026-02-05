# tests/test_resolver.py
import pytest


from src.game.events.out import OutRecordedEvent
from src.game.events.pitch import PitchThrownEvent
from src.player.player_in_game import PlayerInGame
from tests.factories.player_record_factory import make_player_record
from tests.utils import FakeRNG, fake_game, fake_game_with_batter_cycle
from src.game.resolver import Resolver
from src.game.intents.pitch import PitchIntent, PrePitchSituation
from src.game.events.strike import StrikeEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.ball import BallEvent

# from src.game.events.bases import RunnerAdvancedEvent


@pytest.fixture
def pitch_intent():
    return PitchIntent(pitcher="p1", batter="b1", pre_pitch_situation=PrePitchSituation)


@pytest.fixture
def resolver():
    return Resolver(rng=FakeRNG([1, 1, 1, 1]))


def test_resolver_returns_events(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())

    assert len(events) >= 1


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
    rng = FakeRNG([0.1] * 100)
    resolver.set_rng(rng)  # Replace all RNGs at once

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
    out = OutRecordedEvent(reason="out", pitcher=PlayerInGame(make_player_record()))
    out.apply(game)
    assert not game._plate_appearance_complete


def test_pa_end_advances_batter():
    game = fake_game_with_batter_cycle()
    old_batter = game.current_batter
    pae = PlateAppearanceEndEvent("walk", batter=PlayerInGame(make_player_record()))
    pae.apply(game)
    game._post_event()
    assert game.current_batter is not old_batter


def test_three_strikes_ends_plate_appearance_with_strikeout():
    """
    Given three strike outcomes in a row,
    resolver must end the plate appearance exactly once.
    """
    # Assume 0.99 is a strike
    # rng = FakeRNG([0.99] * 10)  # give it 10 because too many are being consumed
    rng = FakeRNG(
        [
            0.99,  # pitch 1 -> strike
            0.99,  # pitch 2 -> strike
            0.99,  # pitch 3 -> strike
        ]
    )
    resolver = Resolver(rng=rng)
    game = fake_game()

    intent = PitchIntent(
        pitcher=PlayerInGame(make_player_record()),
        batter=PlayerInGame(make_player_record()),
    )

    all_events = []

    # Act: resolve three pitches
    for _ in range(3):
        events = resolver.resolve(intent, game)
        all_events.extend(events)

        # Apply events to mutate count
        for e in events:
            e.apply(game)

    # Assert
    strikes = [e for e in all_events if isinstance(e, StrikeEvent)]
    pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]
    outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]

    assert len(strikes) == 3
    assert len(pa_end) == 1
    assert pa_end[0].reason == "strikeout"
    assert len(outs) == 1


# # Layer 2
def test_pitch_thrown_is_first_event(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())
    assert isinstance(events[0], PitchThrownEvent)


def test_pa_end_is_last_if_present(resolver, pitch_intent):
    events = resolver.resolve(pitch_intent, fake_game())
    pa_end = [e for e in events if isinstance(e, PlateAppearanceEndEvent)]

    if pa_end:
        assert events[-1] is pa_end[0]


# # layer 3


def test_walk_events():
    rng = FakeRNG([0.1] * 4)  # 0.1 is assumed to be a ball
    game = fake_game()
    resolver = Resolver(rng=rng)
    # events = resolver.resolve(pitch_intent, game)

    intent = PitchIntent(
        pitcher=PlayerInGame(make_player_record()),
        batter=PlayerInGame(make_player_record()),
        pre_pitch_situation=PrePitchSituation,
    )

    all_events = []

    for _ in range(4):
        events = resolver.resolve(intent, game)
        all_events.extend(events)

        # Apply events to mutate count
        for e in events:
            e.apply(game)

    # Assert
    balls = [e for e in all_events if isinstance(e, BallEvent)]
    pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]
    outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]

    assert len(balls) == 4
    assert len(pa_end) == 1
    assert pa_end[0].reason == "walk"
    assert len(outs) == 0


def assert_event_types(events, types):
    assert [type(e) for e in events] == types
