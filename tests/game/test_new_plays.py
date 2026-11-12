"""
Plays added 2026-11-12: dropped third strikes, catcher pickoffs, pickoff
errors charged to whoever erred, line drives (doubled off) and runners
thrown out tagging up.

The resolver's RNG is scripted so each test forces one branch.
"""

from types import SimpleNamespace

import pytest

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.events.error import ErrorChargedEvent
from src.game.events.out import (
    AirDoublePlayEvent,
    LineOutEvent,
    OutRecordedEvent,
    PutOutEvent,
)
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.pick_off import (
    CatcherPickoffErrorEvent,
    CatcherPickoffSuccessEvent,
    PickoffErrorEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.sacrifice import SacFlyEvent
from src.game.events.strike import DroppedThirdStrikeEvent
from src.game.events.strikeout import StrikeOutEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.intents.pick_off import PickOffIntent
from src.game.intents.pitch import PitchIntent, PrePitchSituation
from src.game.resolvers.catcher_pickoff import (
    catcher_pickoff_success_prob,
    resolve_catcher_pickoff,
)
from src.game.resolvers.outs import resolve_fly_out
from src.game.resolvers.pick_off import resolve_pickoff
from src.game.resolvers.pitch import resolve_strike
from src.game.resolvers.sacrifices import resolve_sac_fly
from src.api.view_models.play_by_play import describe
from tests.game.test_play_errors import _resolver, _player, _of, _batter_to
from tests.test_double_play_third_out import MockGame


@pytest.fixture
def game():
    g = MockGame()
    g.count = SimpleNamespace(balls=0, strikes=2)
    g.situation = PrePitchSituation()
    return g


@pytest.fixture
def intent():
    return PitchIntent(pitcher=_player("sp"), batter=_player("cf"))


# --- dropped third strikes --------------------------------------------------


def test_strike_three_held_is_a_plain_strikeout(game, intent):
    events = resolve_strike(_resolver(0.99), "swinging_strike", intent, game)
    assert not _of(events, DroppedThirdStrikeEvent)
    assert _of(events, PlateAppearanceEndEvent)[0].reason == "strikeout"


def test_no_dropped_third_strike_with_first_occupied_and_less_than_two_outs(
    game, intent
):
    game.bases.set_runner(FIRST, _player())
    events = resolve_strike(_resolver(0.0), "swinging_strike", intent, game)
    assert not _of(events, DroppedThirdStrikeEvent)
    assert len(_of(events, OutRecordedEvent)) == 1


def test_dropped_third_strike_ball_gets_away_batter_reaches(game, intent):
    # dropped, gets away, wild pitch
    events = resolve_strike(_resolver(0.0, 0.0, 0.0), "swinging_strike", intent, game)
    assert _of(events, DroppedThirdStrikeEvent)
    assert _of(events, StrikeOutEvent)  # still a K
    assert _of(events, WildPitchEvent)
    assert not _of(events, OutRecordedEvent)
    assert _batter_to(events, intent.batter) == [FIRST]
    assert _of(events, PlateAppearanceEndEvent)[0].reason == "strikeout_wild_pitch"


def test_dropped_third_strike_passed_ball_with_two_outs(game, intent):
    game.inning.outs = 2
    game.bases.set_runner(FIRST, _player())
    events = resolve_strike(_resolver(0.0, 0.0, 0.99), "swinging_strike", intent, game)
    assert _of(events, PassedBallEvent)
    assert _batter_to(events, intent.batter) == [FIRST]


def test_dropped_third_strike_thrown_out_at_first(game, intent):
    # dropped, doesn't get away, not tagged, good throw
    events = resolve_strike(
        _resolver(0.0, 0.99, 0.99, 0.99), "swinging_strike", intent, game
    )
    po = _of(events, PutOutEvent)[0]
    assert po.fielder is game.pos("1b") and po.assist is game.pos("c")
    assert len(_of(events, OutRecordedEvent)) == 1
    assert _of(events, PlateAppearanceEndEvent)[0].reason == "strikeout_dropped"


def test_dropped_third_strike_wild_throw_puts_him_on(game, intent):
    runner = _player()
    game.bases.set_runner(SECOND, runner)
    events = resolve_strike(
        _resolver(0.0, 0.99, 0.99, 0.0), "swinging_strike", intent, game
    )
    err = _of(events, ErrorChargedEvent)
    assert err and err[0].fielder is game.pos("c")
    assert not _of(events, OutRecordedEvent)
    assert _batter_to(events, intent.batter) == [FIRST]
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[runner] == THIRD


def test_called_strike_three_is_dropped_less_often(game, intent):
    # 0.04 is under a swinging drop chance but over a called one
    sw = resolve_strike(_resolver(0.04), "swinging_strike", intent, game)
    called = resolve_strike(_resolver(0.04), "called_strike", intent, game)
    assert _of(sw, DroppedThirdStrikeEvent)
    assert not _of(called, DroppedThirdStrikeEvent)


# --- pickoffs ---------------------------------------------------------------


def test_pickoff_drop_is_charged_to_the_first_baseman(game):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    pitcher = _player("sp")
    intent = PickOffIntent(pitcher=pitcher, target_base=FIRST)
    succ, throw, drop = 0.0, 0.0, 0.0
    # Not out; past the pitcher's throwing error, inside the drop.
    from src.game.resolvers.pick_off import adjust_pickoff_success

    succ, throw, drop = adjust_pickoff_success(
        _resolver(),
        FIRST,
        pitcher,
        game,
        runner.skills["base_running"],
        cover=game.pos("1b"),
    )
    r = succ + throw + drop / 2
    events = resolve_pickoff(_resolver(r), intent, game)
    err = _of(events, PickoffErrorEvent)
    assert err and err[0].fielder is game.pos("1b")


def test_pickoff_bad_throw_is_the_pitchers(game):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    pitcher = _player("sp")
    from src.game.resolvers.pick_off import adjust_pickoff_success

    succ, throw, _ = adjust_pickoff_success(
        _resolver(),
        FIRST,
        pitcher,
        game,
        runner.skills["base_running"],
        cover=game.pos("1b"),
    )
    events = resolve_pickoff(
        _resolver(succ + throw / 2),
        PickOffIntent(pitcher=pitcher, target_base=FIRST),
        game,
    )
    assert _of(events, PickoffErrorEvent)[0].fielder is pitcher


def test_catcher_pickoff_gets_the_runner(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    # target first, attempt, out
    events = resolve_catcher_pickoff(_resolver(0.0, 0.0, 0.0), intent, game)
    assert _of(events, CatcherPickoffSuccessEvent)
    po = _of(events, PutOutEvent)[0]
    assert po.fielder is game.pos("1b") and po.assist is game.pos("c")
    assert _of(events, RunnerRemovedEvent)[0].runner is runner


def test_catcher_pickoff_usually_not_tried(game, intent):
    game.bases.set_runner(FIRST, _player())
    assert resolve_catcher_pickoff(_resolver(0.0, 0.5), intent, game) == []


def test_catcher_pickoff_throw_away_moves_runners(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    catcher = game.pos("c")
    p_out = catcher_pickoff_success_prob(catcher, runner)
    events = resolve_catcher_pickoff(_resolver(0.0, 0.0, p_out + 0.001), intent, game)
    err = _of(events, CatcherPickoffErrorEvent)
    assert err and err[0].fielder is catcher
    moved = {e.runner: e.to_base for e in _of(events, RunnerAdvancedEvent)}
    assert moved[runner] == SECOND


def test_careless_runners_get_picked_off_more():
    catcher = _player("c")
    smart = SimpleNamespace(skills={"base_running": 80})
    sloppy = SimpleNamespace(skills={"base_running": 30})
    assert catcher_pickoff_success_prob(catcher, sloppy) > catcher_pickoff_success_prob(
        catcher, smart
    )


# --- line drives and tag-ups -----------------------------------------------


def test_infield_liner_doubles_off_a_runner_who_was_going(game, intent):
    runner = _player()
    game.bases.set_runner(FIRST, runner)
    game.situation = PrePitchSituation(steal_attempt=FIRST)
    # liner, to the infield, doubled off
    events = resolve_fly_out(_resolver(0.0, 0.0, 0.0), intent, game)
    dp = _of(events, AirDoublePlayEvent)
    assert dp and dp[0].kind == "line" and dp[0].runner is runner
    assert len(_of(events, OutRecordedEvent)) == 2
    assert _of(events, PlateAppearanceEndEvent)[0].reason == "line_drive_double_play"


def test_infield_liner_with_nobody_on_is_a_line_out(game, intent):
    events = resolve_fly_out(_resolver(0.0, 0.0), intent, game)
    assert _of(events, LineOutEvent)
    assert len(_of(events, OutRecordedEvent)) == 1
    assert _of(events, PlateAppearanceEndEvent)[0].reason == "line_out"


def test_no_double_off_with_two_outs(game, intent):
    game.inning.outs = 2
    game.bases.set_runner(FIRST, _player())
    game.situation = PrePitchSituation(steal_attempt=FIRST)
    events = resolve_fly_out(_resolver(0.0, 0.0, 0.0), intent, game)
    assert not _of(events, AirDoublePlayEvent)
    assert len(_of(events, OutRecordedEvent)) == 1


def test_runner_thrown_out_at_home_on_a_sac_fly(game, intent):
    runner = _player()
    game.bases.set_runner(THIRD, runner)
    events = resolve_sac_fly(_resolver(0.0), intent, game)
    assert not _of(events, SacFlyEvent)
    dp = _of(events, AirDoublePlayEvent)
    assert dp and dp[0].kind == "fly" and dp[0].base == HOME
    assert not [e for e in _of(events, RunnerAdvancedEvent) if e.to_base == HOME]
    assert _of(events, PutOutEvent)[1].fielder is game.pos("c")


def test_runner_thrown_out_tagging_to_third(game, intent):
    runner = _player()
    game.bases.set_runner(SECOND, runner)
    # fly ball (not liner), not dropped, tags (0.0), thrown out (0.0)
    events = resolve_fly_out(_resolver(0.99, 0.99, 0.0, 0.0), intent, game)
    dp = _of(events, AirDoublePlayEvent)
    assert dp and dp[0].base == THIRD
    assert _of(events, RunnerRemovedEvent)[0].runner is runner


# --- play-by-play words ----------------------------------------------------


@pytest.mark.parametrize(
    "play, words",
    [
        ({"b": "A. B", "r": "strikeout_wild_pitch"}, "reaches first on a wild pitch"),
        ({"b": "A. B", "r": "strikeout_dropped", "f": ["1b", "c"]}, "catcher to first"),
        ({"b": "A. B", "r": "line_out", "f": ["ss", None]}, "lines out to short"),
        (
            {
                "b": "A. B",
                "r": "line_drive_double_play",
                "f": ["2b", None],
                "d": ["C. D", 1],
            },
            "C. D is doubled off first",
        ),
        (
            {"b": "A. B", "r": "fly_double_play", "f": ["rf", "c"], "d": ["C. D", 4]},
            "thrown out at home tagging up",
        ),
        ({"b": None, "n": [["cpo", "C. D", 1]]}, "picked off first by the catcher"),
        ({"b": None, "n": [["poe", None, "1b"]]}, "first baseman drops the pickoff"),
    ],
)
def test_play_by_play_words(play, words):
    assert words in describe(play)
