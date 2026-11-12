"""
Errors on plays that used to always succeed: double plays, fielder's
choices, sac bunts, sac flies, fly balls, steals and base hits.

The resolver's RNG is scripted so each test forces one branch.
"""

from types import SimpleNamespace

import pytest

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.events.double_play import DoublePlayEvent
from src.game.events.error import (
    FieldingErrorEvent,
    ThrowingErrorEvent,
    OutfielderThrowingErrorEvent,
    RunnerAdvancedOnErrorEvent,
)
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.hits import SingleEvent
from src.game.events.out import OutRecordedEvent, PutOutEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.sacrifice import SacBuntEvent
from src.game.events.steal import StolenBaseEvent
from src.game.intents.pitch import PitchIntent
from src.game.resolver import Resolver
from src.game.resolvers.double_play import resolve_double_play
from src.game.resolvers.errors import (
    fielding_error_chance,
    throwing_error_chance,
)
from src.game.resolvers.fielders_choice import resolve_fielders_choice
from src.game.resolvers.hits import resolve_single
from src.game.resolvers.outs import resolve_fly_out
from src.game.resolvers.sacrifices import resolve_sac_bunt, resolve_sac_fly
from src.game.resolvers.steal import resolve_steal_attempt
from src.player.player_in_game import PlayerInGame
from tests.factories.player_record_factory import make_player_record
from tests.test_double_play_third_out import MockGame


class SeqRNG:
    """Returns the scripted values in order, then `rest` forever."""

    def __init__(self, values, rest=0.99):
        self.values = list(values)
        self.rest = rest

    def random(self):
        return self.values.pop(0) if self.values else self.rest

    def choice(self, seq):
        return seq[0]


def _resolver(*values, rest=0.99):
    return Resolver(rng=SeqRNG(values, rest=rest))


def _player(pos="ss"):
    return PlayerInGame(make_player_record(position=pos))


@pytest.fixture
def game():
    return MockGame()


@pytest.fixture
def intent():
    return PitchIntent(pitcher=_player("sp"), batter=_player("cf"))


def _of(events, cls):
    return [e for e in events if isinstance(e, cls)]


def _batter_to(events, batter):
    return [
        e.to_base
        for e in events
        if isinstance(e, RunnerAdvancedEvent)
        and e.runner is batter
        and e.from_base is None
    ]


# --- error chances ----------------------------------------------------------


def test_better_fielders_make_fewer_errors():
    good = SimpleNamespace(
        ratings={"ss": 95}, current_position="ss", skills={"arm": 90}
    )
    bad = SimpleNamespace(ratings={"ss": 40}, current_position="ss", skills={"arm": 30})
    assert fielding_error_chance(good) < fielding_error_chance(bad)
    assert throwing_error_chance(good) < throwing_error_chance(bad)


# --- double plays -----------------------------------------------------------


def test_double_play_can_be_booted(game, intent):
    """Fielder boots the grounder: nobody out, everyone moves up."""
    first, third = _player(), _player()
    game.bases.set_runner(FIRST, first)
    game.bases.set_runner(THIRD, third)

    events = resolve_double_play(_resolver(0.0), intent, game)

    assert not _of(events, DoublePlayEvent)
    assert not _of(events, OutRecordedEvent)
    assert len(_of(events, FieldingErrorEvent)) == 1
    assert _batter_to(events, intent.batter) == [FIRST]
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[first] == SECOND
    assert moved[third] == HOME


def test_wild_relay_costs_the_second_out_and_an_extra_base(game, intent):
    """Lead out made (4-6-3), relay sails: batter to second, error on the pivot."""
    runner = _player()
    game.bases.set_runner(FIRST, runner)

    # 0.99: lead out is clean; 0.0: the relay is wild.
    events = resolve_double_play(_resolver(0.99, 0.0), intent, game)

    assert not _of(events, DoublePlayEvent)
    assert len(_of(events, OutRecordedEvent)) == 1
    err = _of(events, ThrowingErrorEvent)
    assert len(err) == 1
    assert err[0].fielder is game.pos("ss")  # 4-6-3: shortstop's relay
    assert _of(events, RunnerRemovedEvent)[0].runner is runner
    assert _batter_to(events, intent.batter) == [SECOND]


def test_clean_double_play_still_gets_two(game, intent):
    game.bases.set_runner(FIRST, _player())
    events = resolve_double_play(_resolver(rest=0.99), intent, game)
    assert len(_of(events, DoublePlayEvent)) == 1
    assert len(_of(events, OutRecordedEvent)) == 2
    assert not _of(events, FieldingErrorEvent) + _of(events, ThrowingErrorEvent)


# --- fielder's choice / sacrifices -----------------------------------------


def test_fielders_choice_can_be_botched(game, intent):
    game.bases.set_runner(FIRST, _player())
    # rng: fielder pick (0.5 twice), then the error check
    events = resolve_fielders_choice(_resolver(0.5, 0.5, 0.0), intent, game)
    assert not _of(events, FieldersChoiceEvent)
    assert not _of(events, OutRecordedEvent)
    assert _of(events, FieldingErrorEvent)
    assert _batter_to(events, intent.batter) == [FIRST]


def test_sac_bunt_can_be_botched(game, intent):
    game.bases.set_runner(FIRST, _player())
    events = resolve_sac_bunt(_resolver(0.0), intent, game)
    assert not _of(events, SacBuntEvent)
    assert not _of(events, OutRecordedEvent)
    assert _of(events, FieldingErrorEvent)


def test_bad_throw_home_on_sac_fly_moves_trailing_runner_two(game, intent):
    trailer = _player()
    game.bases.set_runner(THIRD, _player())
    game.bases.set_runner(FIRST, trailer)
    # 0.99: the runner beats the throw; 0.0: the throw gets away
    events = resolve_sac_fly(_resolver(0.99, 0.0), intent, game)
    assert len(_of(events, OutRecordedEvent)) == 1
    assert _of(events, OutfielderThrowingErrorEvent)
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[trailer] == THIRD


# --- outfield ---------------------------------------------------------------


def test_fly_ball_can_be_dropped(game, intent):
    # 0.99: a fly ball, not a liner; 0.0: dropped; 0.99: batter holds at first
    events = resolve_fly_out(_resolver(0.99, 0.0, 0.99), intent, game)
    assert not _of(events, OutRecordedEvent)
    assert not _of(events, PutOutEvent)
    assert _of(events, FieldingErrorEvent)
    assert _batter_to(events, intent.batter) == [FIRST]


def test_bobbled_single_gives_everyone_an_extra_base(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    # Runner holds at second (0.99, 0.99), then the bobble (0.0).
    events = resolve_single(_resolver(0.99, 0.99, 0.0), intent, game)
    assert len(_of(events, SingleEvent)) == 1  # still a hit
    assert len(_of(events, RunnerAdvancedOnErrorEvent)) == 1
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[runner] == THIRD
    assert moved[intent.batter] == SECOND


# --- steals -----------------------------------------------------------------


def test_catchers_throw_into_center_gives_the_thief_third(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    # 0.0: steal succeeds; 0.0: catcher's throw is wild
    events = resolve_steal_attempt(_resolver(0.0, 0.0), FIRST, intent, game)
    assert len(_of(events, StolenBaseEvent)) == 1
    err = _of(events, RunnerAdvancedOnErrorEvent)
    assert len(err) == 1 and err[0].fielder is game.pos("c")
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[runner] == THIRD


def test_clean_steal_has_no_error(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    events = resolve_steal_attempt(_resolver(0.0, rest=0.99), FIRST, intent, game)
    assert not _of(events, RunnerAdvancedOnErrorEvent)
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[runner] == SECOND
