# src/game/resolvers/pick_off.py
from typing import List

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.pick_off import (
    PickoffAttemptEvent,
    PickoffSuccessEvent,
    PickoffErrorEvent,
    PickoffFailedEvent,
)
from src.game.intents.pick_off import PickOffIntent
from src.game.events.runners import RunnerRemovedEvent
from src.player.player_in_game import PlayerInGame


def resolve_pickoff(resolver, intent: PickOffIntent, game) -> List[GameEvent]:
    """
    Resolve a pickoff attempt.

    Possible outcomes:
    1. Successful pickoff (runner out)
    2. Failed pickoff (runner safe, no advancement)
    3. Throwing error (runner advances)
    """
    events: list[GameEvent] = []

    base = intent.target_base
    runner = game.bases.runner_on(base)

    if not runner:
        return events

    events.append(PickoffAttemptEvent(base=base, runner=runner, pitcher=intent.pitcher))

    # Determine outcome
    r = resolver.rng.random()

    pickoff_success_prob, pickoff_error_prob = adjust_pickoff_success(
        resolver,
        base,
        intent.pitcher,
        game,
        runner.skills["base_running"],
        intent.steal_on,
    )
    # base_running skill of runner
    if r < pickoff_success_prob:
        # Successful pickoff - runner out
        resolver.logger.debug(f"Successful pickoff at base {base}")
        events.append(
            PickoffSuccessEvent(base=base, runner=runner, pitcher=intent.pitcher)
        )
        if base == THIRD:
            fielder = game.pos("3b")
        elif base == SECOND:
            if resolver.rng.random() < 0.55:
                fielder = game.pos("ss")
            else:
                fielder = game.pos("2b")
        else:
            fielder = game.pos("1b")
        events.append(PutOutEvent(fielder=fielder, assist=intent.pitcher))
        events.append(OutRecordedEvent(reason="pickoff", pitcher=intent.pitcher))
        events.append(
            RunnerRemovedEvent(runner=runner, from_base=base, reason="pickoff")
        )

    elif r < pickoff_success_prob + pickoff_error_prob:
        # Throwing error - runner advances
        resolver.logger.debug(f"Pickoff throwing error at base {base}")
        events.append(
            PickoffErrorEvent(base=base, runner=runner, pitcher=intent.pitcher)
        )
        # Advance all runners one base
        events.extend(
            resolver._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="pickoff_error",
            )
        )

    else:
        # Runner safe, no advancement
        resolver.logger.debug(f"Failed pickoff attempt at base {base}")
        events.append(
            PickoffFailedEvent(base=base, runner=runner, pitcher=intent.pitcher)
        )

    return events


def adjust_pickoff_success(
    resolver, base: int, pitcher: PlayerInGame, game, br_skill=50, steal_on=False
):
    success = resolver.PICKOFF_SUCCESS_PROB
    error = resolver.PICKOFF_ERROR_PROB
    resolver.logger.trace(
        f"pickoff success vars, base={base}, pitcher.throws={pitcher.throws}, baserunning={br_skill}"
    )
    if base is FIRST and pitcher.throws[0].lower() == "l":
        success *= 1.1
    if base is THIRD and pitcher.throws[0].lower() == "r":
        success *= 1.1
    success = success * 50 / max(30, br_skill)
    accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
    error *= 50 / max(30, accuracy)
    if base is FIRST:
        error *= 50 / max(1, game.pos("1b").skills["infield"])
    if base is SECOND:
        r = resolver.rng.random()
        # 50/50 2nd baseman or short stop
        if r < 0.5:
            error *= 50 / max(1, game.pos("2b").skills["infield"])
        else:
            error *= 50 / max(1, game.pos("ss").skills["infield"])
    if base is THIRD:
        error *= 50 / max(1, game.pos("3b").skills["infield"])
    if steal_on:
        success *= resolver.STEAL_ON_PICKOFF_MODIFIER
    return success, error
