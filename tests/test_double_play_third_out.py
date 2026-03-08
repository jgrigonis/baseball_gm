"""
Regression test: runner on 3rd must NOT score when a double play
ends the inning (i.e. the double play produces the 3rd out).

Rule: a run cannot score if the third out of an inning is a force play,
or if the batter-runner is retired before reaching first base.

Scenario (from the bug report):
  - 1 out, runners on 1st and 3rd
  - Batter hits into a double play  →  2nd out (runner on 1st, force) + 3rd out (batter at 1st)
  - Runner from 3rd crosses the plate, but the inning is already over on a force play
  - Run should NOT count
"""

import pytest
from types import SimpleNamespace

from src.game.bases import FIRST, THIRD, HOME
from src.game.events.out import OutRecordedEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.resolvers.double_play import resolve_double_play
from src.player.player_in_game import PlayerInGame
from src.team.lineup_slot import LineupSlot
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

# ---------------------------------------------------------------------------
# Minimal fixtures (mirror the MockGame / MockRNG pattern in test_resolver.py)
# ---------------------------------------------------------------------------


class MockRNG:
    def __init__(self, value=0.5):
        self.value = value

    def random(self):
        return self.value

    def choice(self, seq):
        return seq[0]


class MockBases:
    def __init__(self):
        self._runners: dict = {}
        self.is_empty = True

    def runner_on(self, base):
        return self._runners.get(base)

    def set_runner(self, base, runner):
        self._runners[base] = runner
        self.is_empty = False

    def occupied_map(self):
        return dict(self._runners)


class MockGame:
    def __init__(self):
        self.bases = MockBases()
        self.inning = SimpleNamespace(outs=0)
        self.rng = MockRNG(0.5)

        # Build a minimal pitch_team with all fielder positions filled
        self.pitch_team = TeamInGameFactory.from_record(make_team_record())
        positions = {}
        for pos in ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"):
            player = PlayerInGame(make_player_record(position=pos))
            positions[pos] = player
            self.pitch_team.lineup.append(LineupSlot(player=player, position=pos))
        self.pitch_team._positions = positions

        self.current_pitcher = PlayerInGame(make_player_record(position="sp"))
        self.current_batter = PlayerInGame(make_player_record())

    def pos(self, position: str):
        pos_map = {
            "p": self.current_pitcher,
            **self.pitch_team._positions,
        }
        return pos_map[position]


@pytest.fixture
def game():
    return MockGame()


@pytest.fixture
def pitch_intent():
    from src.game.intents.pitch import PitchIntent

    return PitchIntent(
        pitcher=PlayerInGame(make_player_record(position="sp")),
        batter=PlayerInGame(make_player_record()),
    )


@pytest.fixture
def resolver():
    from src.game.resolver import Resolver

    return Resolver(rng=MockRNG(0.5))


# ---------------------------------------------------------------------------
# The regression test
# ---------------------------------------------------------------------------


class TestDoublePlayRunnerOnFirstAndThird:
    """
    Covers the bug where a run was incorrectly scored when a double play
    ended the inning (third out) with runners on 1st and 3rd.
    """

    def test_run_does_not_score_when_dp_ends_inning(self, resolver, game, pitch_intent):
        """
        With 1 out and runners on 1st and 3rd, a double play produces the
        2nd and 3rd outs.  The runner crossing from 3rd should NOT score
        because the third out is a force play.
        """
        game.inning.outs = 1
        runner_on_first = PlayerInGame(make_player_record())
        runner_on_third = PlayerInGame(make_player_record())
        game.bases.set_runner(FIRST, runner_on_first)
        game.bases.set_runner(THIRD, runner_on_third)

        events = resolve_double_play(resolver, pitch_intent, game)

        # Sanity: two outs must be recorded (bringing total to 3)
        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        assert len(outs) == 2, "Double play should record exactly 2 outs"

        # The runner on first must be removed (force out)
        removed = [e for e in events if isinstance(e, RunnerRemovedEvent)]
        removed_runners = [e.runner for e in removed]
        assert (
            runner_on_first in removed_runners
        ), "Runner on first should be removed on force out"

        # *** The key assertion: runner from 3rd must NOT reach HOME ***
        runner_scored = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner == runner_on_third
                and e.to_base == HOME
            ),
            None,
        )
        assert runner_scored is None, (
            "Runner from third must NOT score when the double play produces "
            "the 3rd out of the inning (force-play third out rule)"
        )

    def test_run_does_score_when_dp_does_not_end_inning(
        self, resolver, game, pitch_intent
    ):
        """
        Counterpart: with 0 outs the double play only gets to 2 outs total,
        so a runner who crosses from 3rd before the final force out CAN score.
        (This verifies we haven't broken the normal case.)
        """
        game.inning.outs = 0
        runner_on_first = PlayerInGame(make_player_record())
        runner_on_third = PlayerInGame(make_player_record())
        game.bases.set_runner(FIRST, runner_on_first)
        game.bases.set_runner(THIRD, runner_on_third)

        events = resolve_double_play(resolver, pitch_intent, game)

        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        assert len(outs) == 2

        # With only 2 outs reached (0 + 2 = 2), the run IS valid
        runner_scored = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner == runner_on_third
                and e.to_base == HOME
            ),
            None,
        )
        assert (
            runner_scored is not None
        ), "Runner from third SHOULD score on a double play that ends with only 2 outs total"
