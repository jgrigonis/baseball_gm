# tests/test_resolver.py
import pytest


from src.game.events.out import OutRecordedEvent
from src.game.events.pitch import PitchThrownEvent
from tests.utils import FakeRNG, fake_game, fake_game_with_batter_cycle, real_game
from src.game.resolver import Resolver
from src.game.intents.pitch import PitchIntent
from src.game.events.strike import StrikeEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import OutRecordedEvent
from src.game.events.ball import BallEvent

# from src.game.events.bases import RunnerAdvancedEvent


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
    assert not game._plate_appearance_complete


def test_pa_end_advances_batter():
    game = fake_game_with_batter_cycle()
    old_batter = game.current_batter
    pae = PlateAppearanceEndEvent("walk")
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
        pitcher_id="p1",
        batter_id="b1",
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
        pitcher_id="p1",
        batter_id="b1",
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


def test_walk_puts_batter_on_first():
    rng = FakeRNG([0.1] * 4)
    game = real_game(rng=rng)
    game._sync_players()

    batter = game.current_batter.player

    # Step until PA completes
    for _ in range(4):
        game.step()

    assert game.count.balls == 0
    assert game.count.strikes == 0
    assert game.bases.runner_on(1) is batter


# BAD old test
# def test_walk_puts_batter_on_first():
#     rng = FakeRNG([0.1] * 10)
#     resolver = Resolver(rng=rng)
#     game = fake_game()

#     batter = game.current_batter.player
#     intent = PitchIntent("p", batter.id)

#     for _ in range(4):
#         events = resolver.resolve(intent, game)
#         for e in events:
#             e.apply(game)

#     assert game.count.balls == 0
#     assert game.count.strikes == 0

#     assert game.bases.occupied_bases() == [0]

#     assert game.bases.runner_on(0) is batter

# pseudocode
# def test_force_chain_stops_on_empty_base():
#     bases: runner on 1st only
#     force starting_base=0
#     assert only one RunnerAdvancedEvent


# def test_three_strikes_results_in_strikeout():
#     rng = FakeRNG([0.9] * 10)  # always strike
#     resolver = Resolver(rng=rng)
#     game = fake_game()

#     intent = PitchIntent("p", "b")
#     all_events = []

#     for _ in range(3):
#         events = resolver.resolve(intent, game)
#         for e in events:
#             e.apply(game)
#         all_events.extend(events)

#     strikes = [e for e in all_events if isinstance(e, StrikeEvent)]
#     outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]
#     pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]

#     assert len(strikes) == 3
#     assert len(outs) == 1
#     assert outs[0].reason == "strikeout"
#     assert len(pa_end) == 1

# def test_four_consecutive_walks_load_bases_and_score_run():
#     rng = FakeRNG([0.1] * 50)
#     resolver = Resolver(rng=rng)
#     game = fake_game()

#     for _ in range(4):
#         intent = PitchIntent(
#             pitcher_id="p",
#             batter_id=game.current_batter.player.id
#         )
#         for _ in range(4):
#             events = resolver.resolve(intent, game)
#             for e in events:
#                 e.apply(game)

#     assert game.bases.occupied(1)
#     assert game.bases.occupied(2)
#     assert game.bases.occupied(3)
#     assert game.score.away == 1

# def test_pa_end_advances_batter_and_resets_count():
#     game = fake_game()
#     old_batter = game.current_batter

#     PlateAppearanceEndEvent("walk").apply(game)
#     game._post_event()

#     assert game.current_batter is not old_batter
#     assert game.count.balls == 0
#     assert game.count.strikes == 0


# fake_game doesn't seem to handle this
# def test_four_walk_events():
#     rng = FakeRNG([0.1] * 16)  # 0.1 is assumed to be a ball
#     game = fake_game()
#     resolver = Resolver(rng=rng)
#     # events = resolver.resolve(pitch_intent, game)

#     intent0 = PitchIntent(
#         pitcher_id="p1",
#         batter_id="b0",
#     )

#     intent1 = PitchIntent(
#         pitcher_id="p1",
#         batter_id="b1",
#     )

#     intent2 = PitchIntent(
#         pitcher_id="p1",
#         batter_id="b2",
#     )

#     intent3 = PitchIntent(
#         pitcher_id="p1",
#         batter_id="b3",
#     )

#     all_events = []

#     for _ in range(4):
#         events = resolver.resolve(intent0, game)
#         all_events.extend(events)

#         # Apply events to mutate count
#         for e in events:
#             print(e)
#             e.apply(game)

#     balls = [e for e in all_events if isinstance(e, BallEvent)]
#     pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]
#     outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]

#     assert len(balls) == 4
#     assert len(pa_end) == 1
#     assert pa_end[0].reason == "walk"

#     for _ in range(4):
#         events = resolver.resolve(intent1, game)
#         all_events.extend(events)

#         # Apply events to mutate count
#         for e in events:
#             print(e)
#             e.apply(game)

#     balls = [e for e in all_events if isinstance(e, BallEvent)]
#     pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]
#     outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]

#     assert len(balls) == 8
#     assert len(pa_end) == 2
#     assert pa_end[1].reason == "walk"

#     for _ in range(4):
#         events = resolver.resolve(intent2, game)
#         all_events.extend(events)

#         # Apply events to mutate count
#         for e in events:
#             e.apply(game)

#     for _ in range(4):
#         events = resolver.resolve(intent3, game)
#         all_events.extend(events)

#         # Apply events to mutate count
#         for e in events:
#             e.apply(game)

#     # Assert
#     balls = [e for e in all_events if isinstance(e, BallEvent)]
#     pa_end = [e for e in all_events if isinstance(e, PlateAppearanceEndEvent)]
#     outs = [e for e in all_events if isinstance(e, OutRecordedEvent)]

#     assert len(balls) == 16
#     assert len(pa_end) == 4
#     assert pa_end[0].reason == "walk"
#     assert pa_end[1].reason == "walk"
#     assert pa_end[2].reason == "walk"
#     assert pa_end[3].reason == "walk"
#     assert len(outs) == 0

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


def assert_event_types(events, types):
    assert [type(e) for e in events] == types
