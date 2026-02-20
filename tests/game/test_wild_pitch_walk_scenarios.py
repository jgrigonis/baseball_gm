# tests/game/test_wild_pitch_walk_scenarios.py

import pytest
import random

from src.game.game import Game
from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.count import Count

from src.game.resolver import Resolver
from src.game.events.wild_pitch import WildPitchEvent
from src.game.events.walk import WalkEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.intents.pitch import PrePitchSituation
from src.player.player_factory import PlayerFactory
from src.player.player_in_game import PlayerInGame
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS  # Import SKILLS from positions


class ControlledResolver(Resolver):
    """Resolver that returns predetermined outcomes for testing"""

    def __init__(self, scripted_outcomes=None, seed=42):
        """
        Args:
            scripted_outcomes: List of outcomes to return in order
                              e.g., ["wild_pitch", "ball", "strike"]
            seed: Random seed for non-scripted randomness (default: 42)
        """
        super().__init__(rng=random.Random(seed))
        self.scripted_outcomes = scripted_outcomes or []
        self.outcome_index = 0

    def determine_pitch_outcome(self, intent, game):
        """Return scripted outcome instead of random"""
        if self.outcome_index < len(self.scripted_outcomes):
            outcome = self.scripted_outcomes[self.outcome_index]
            self.outcome_index += 1
            return outcome
        raise RuntimeError("No more scripted outcomes available")


def create_test_team(name):
    """Helper to create a test team"""
    from src.team.team_record import TeamRecord
    from src.team.team_in_game_factory import TeamInGameFactory

    players = [create_test_player(f"{name}_P{i}") for i in range(25)]

    tr = TeamRecord(id=f"team_{name}", city=name, mascot="Test", players=tuple(players))
    return TeamInGameFactory.from_record(tr)


def create_test_player(player_id, **skill_overrides):
    """Helper to create test player with controllable skills"""
    from src.player.player_record import PlayerRecord

    # Default average skills - use SKILLS from positions.py
    skills_dict = {skill: 50 for skill in SKILLS}
    skills_dict.update(skill_overrides)

    return PlayerRecord(
        id=player_id,
        first_name="Test",
        last_name=player_id,
        bats="R",
        throws="R",
        skills=PlayerSkills(skills_dict),
        position="1b",
    )


@pytest.fixture
def game():
    """Create a basic game setup - used as fixture parameter"""
    # You'll need to adjust this based on your actual Game constructor
    game = Game(
        home_team=create_test_team("Home"),
        away_team=create_test_team("Away"),
        # ... other params
    )
    return game


class TestWildPitchWalkScenarios:
    """Test wild pitch on 4th ball scenarios"""

    def test_wild_pitch_walk_empty_bases_no_advancement(self, game):
        """
        Wild pitch on ball 4 with empty bases.
        Expected: Walk occurs, no wild pitch advancement (bases empty).

        Args:
            game: Game fixture (automatically injected by pytest)
        """
        # Setup
        game.count = Count(balls=3, strikes=0)  # 3-0 count
        assert game.bases.is_empty

        # Use controlled resolver
        resolver = ControlledResolver(scripted_outcomes=["wild_pitch"])
        game.resolver = resolver
        game.home.set_lineup()
        game.away.set_lineup()
        game._sync_players()
        batter = game.current_batter.player
        # Execute
        for _ in range(6):
            game.step()

        # Assertions
        # 1. Batter walked
        assert game.bases.runner_on(FIRST) is not None
        assert game.bases.runner_on(FIRST) == batter

        # 2. Count reset
        assert game.count.balls == 0
        assert game.count.strikes == 0

    def test_wild_pitch_walk_runner_on_first(self, game):
        """Wild pitch on ball 4 with runner on first."""
        from tests.helpers.event_recorder import EventRecorder
        from tests.helpers.game_helpers import drain_event_queue

        # Setup
        game.count = Count(balls=3, strikes=0)

        pf = PlayerFactory()
        runner = pf.create()
        game.bases.place_runner(FIRST, runner)

        # Controlled resolver
        game.resolver = ControlledResolver(scripted_outcomes=["wild_pitch"])
        game.home.set_lineup()
        game.away.set_lineup()
        game._sync_players()

        initial_batter = game.current_batter.player

        # Execute with event recording
        with EventRecorder(game) as recorder:
            drain_event_queue(game)

        # Verify events
        recorder.assert_event_count(WildPitchEvent, 1)
        recorder.assert_event_count(WalkEvent, 1)

        # Check runner advancements
        advance_events = recorder.get_events(RunnerAdvancedEvent)

        # Runner on first should advance to second
        runner_advances = [e for e in advance_events if e.runner == runner]
        assert len(runner_advances) == 1, "Runner should advance exactly once"
        assert runner_advances[0].from_base == FIRST
        assert runner_advances[0].to_base == SECOND
        assert runner_advances[0].reason == "wild_pitch"

        # Batter should walk to first
        batter_advances = [
            e
            for e in advance_events
            if hasattr(e.runner, "id") and e.runner.id == initial_batter.id
        ]
        assert len(batter_advances) == 1, "Batter should advance exactly once"
        assert batter_advances[0].from_base is None
        assert batter_advances[0].to_base == FIRST
        assert batter_advances[0].reason == "walk"

        # Final state
        assert game.bases.runner_on(FIRST).id == initial_batter.id
        assert game.bases.runner_on(SECOND) == runner
        assert game.bases.runner_on(THIRD) is None

    def test_wild_pitch_walk_bases_loaded(self, game):
        """
        Wild pitch on ball 4 with bases loaded.
        Expected:
        - All runners advance one base (wild pitch)
        - Runner on third scores (wild pitch, not walk RBI)
        - Batter walks to first
        - No double advancement

        Args:
            game: Game fixture
        """
        from tests.helpers.event_recorder import EventRecorder
        from tests.helpers.game_helpers import drain_event_queue

        # Setup
        game.count = Count(balls=3, strikes=0)

        # Load the bases with actual PlayerInGame objects
        pf = PlayerFactory()
        runner_1 = PlayerInGame(pf.create())
        runner_2 = PlayerInGame(pf.create())
        runner_3 = PlayerInGame(pf.create())

        game.bases.place_runner(FIRST, runner_1)
        game.bases.place_runner(SECOND, runner_2)
        game.bases.place_runner(THIRD, runner_3)

        # Controlled resolver
        game.resolver = ControlledResolver(scripted_outcomes=["wild_pitch"])
        game.home.set_lineup()
        game.away.set_lineup()
        game._sync_players()

        initial_batter = game.current_batter.player

        # Execute with event recording
        with EventRecorder(game) as recorder:
            drain_event_queue(game)

        # Assertions
        advance_events = recorder.get_events(RunnerAdvancedEvent)

        # Check each runner advanced exactly once
        r1_advances = [e for e in advance_events if e.runner == runner_1]
        assert len(r1_advances) == 1
        assert r1_advances[0].from_base == FIRST
        assert r1_advances[0].to_base == SECOND
        assert r1_advances[0].reason == "wild_pitch"

        r2_advances = [e for e in advance_events if e.runner == runner_2]
        assert len(r2_advances) == 1
        assert r2_advances[0].from_base == SECOND
        assert r2_advances[0].to_base == THIRD
        assert r2_advances[0].reason == "wild_pitch"

        r3_advances = [e for e in advance_events if e.runner == runner_3]
        assert len(r3_advances) == 1
        assert r3_advances[0].from_base == THIRD
        assert r3_advances[0].to_base == HOME
        assert r3_advances[0].reason == "wild_pitch"
        assert r3_advances[0].rbi_batter is None  # Wild pitch, not RBI

        batter_advances = [
            e
            for e in advance_events
            if hasattr(e.runner, "id") and e.runner.id == initial_batter.id
        ]
        assert len(batter_advances) == 1
        assert batter_advances[0].to_base == FIRST
        assert batter_advances[0].reason == "walk"

        # Final state
        assert game.bases.runner_on(FIRST).id == initial_batter.id
        assert game.bases.runner_on(SECOND) == runner_1
        assert game.bases.runner_on(THIRD) == runner_2

    def test_wild_pitch_walk_runner_on_third_only(self, game):
        """
        Wild pitch on ball 4 with only runner on third.
        Expected:
        - Runner on third scores (wild pitch)
        - Batter walks to first
        - First base was empty during wild pitch, now has batter

        Args:
            game: Game fixture
        """
        from tests.helpers.event_recorder import EventRecorder
        from tests.helpers.game_helpers import drain_event_queue

        # Setup
        game.count = Count(balls=3, strikes=0)

        # Create actual PlayerInGame object
        pf = PlayerFactory()
        runner_3 = PlayerInGame(pf.create())

        game.bases.place_runner(THIRD, runner_3)

        # Controlled resolver
        game.resolver = ControlledResolver(scripted_outcomes=["wild_pitch"])
        game.home.set_lineup()
        game.away.set_lineup()
        game._sync_players()

        initial_batter = game.current_batter.player

        # Instead of setting game.situation (gets overwritten by step()),
        # resolve and pre-load the queue directly
        from src.game.intents.pitch import PitchIntent

        intent = PitchIntent(
            batter=initial_batter,
            pitcher=game.current_pitcher,
            pre_pitch_situation=PrePitchSituation(
                steal_attempt=False,
                double_steal_attempt=None,
                bunt_attempt=False,
                hit_and_run=False,
                pitch_out=False,
                intentional_walk=False,
                pickoff_attempt=None,
            ),
        )

        with EventRecorder(game) as recorder:
            events = game.resolver.resolve(intent, game)
            game._enqueue(events)
            drain_event_queue(game)

        # Debug: print what was captured
        print(f"\nTotal events captured: {len(recorder.events)}")
        for i, event in enumerate(recorder.events):
            print(f"  {i}: {type(event).__name__}", end="")
            if isinstance(event, RunnerAdvancedEvent):
                print(
                    f" - runner={event.runner}, {event.from_base}->{event.to_base}, reason={event.reason}"
                )
            else:
                print()

        # Assertions
        advance_events = recorder.get_events(RunnerAdvancedEvent)

        # Runner on third advances
        r3_advances = [e for e in advance_events if e.runner == runner_3]
        assert len(r3_advances) == 1
        assert r3_advances[0].from_base == THIRD
        assert r3_advances[0].to_base == HOME
        assert r3_advances[0].reason == "wild_pitch"

        # Batter walks
        batter_advances = [
            e
            for e in advance_events
            if hasattr(e.runner, "id") and e.runner.id == initial_batter.id
        ]
        assert len(batter_advances) == 1
        assert batter_advances[0].to_base == FIRST
        assert batter_advances[0].reason == "walk"

        # Total: exactly 2 advancements
        assert len(advance_events) == 2

        # Final state
        assert game.bases.runner_on(FIRST).id == initial_batter.id
        assert game.bases.runner_on(SECOND) is None
        assert game.bases.runner_on(THIRD) is None
