# src/game/resolvers/sacrifices.py
from typing import List

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.events.sacrifice import SacBuntEvent, SacFlyEvent
from src.player.player_in_game import PlayerInGame


def resolve_sac_bunt(resolver, intent, game) -> List[GameEvent]:
    """
    A sac bunt must be a bunt. There can't be 2 outs.

    - move a runner from 1st to 2nd if no other runners
    - move a runner from 2nd to third if no other runners
    - score a runner from 3rd if no other runners
    - all runners should advance if multiple.
    - put out the batter
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runners=True)

    events: list[GameEvent] = []

    events.append(SacBuntEvent(batter=intent.batter))
    events.append(PutOutEvent(game.pos("1b"), _select_infielder_bunt(resolver, game)))
    events.append(OutRecordedEvent(reason="sac_bunt", pitcher=intent.pitcher))

    # Advance all runners one base
    events.extend(
        resolver._advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=1,
            reason="sac_bunt",
            rbi_batter=intent.batter,
        )
    )

    events.append(PlateAppearanceEndEvent(reason="sac_bunt", batter=intent.batter))

    return events


def _select_infielder_bunt(resolver, game) -> PlayerInGame:
    """Randomly select which infielder fields a bunted ball"""
    position = resolver.infielder_bunt_choice.choose()

    position_map = {
        "shortstop": game.pos("ss"),
        "second_baseman": game.pos("2b"),
        "third_baseman": game.pos("3b"),
        "first_baseman": game.pos("1b"),
        "pitcher": game.pos("p"),
        "catcher": game.pos("c"),
    }

    return position_map[position]


def resolve_sac_fly(resolver, intent, game) -> List[GameEvent]:
    """
    A sac fly must result in a score. There can't be 2 outs.

    - score the runner on third
    - put out the batter
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runner_on=THIRD)

    events: list[GameEvent] = []

    events.append(SacFlyEvent(batter=intent.batter))
    events.append(PutOutEvent(resolver._select_outfielder(game)))
    events.append(OutRecordedEvent(reason="sac_fly", pitcher=intent.pitcher))

    runner = game.bases.runner_on(THIRD)
    events.append(
        RunnerAdvancedEvent(
            runner=runner,
            from_base=THIRD,
            to_base=HOME,
            reason="sac_fly",
            rbi_batter=intent.batter,
            pitcher=intent.pitcher,
        )
    )
    # Advance the runners from first and second also
    # Should be a variable chance to change this.
    events.extend(
        resolver._advance_all_runners(
            game,
            (SECOND, FIRST),
            advancement=1,
            reason="ground_out",
        )
    )

    events.append(PlateAppearanceEndEvent(reason="sac_fly", batter=intent.batter))

    return events
