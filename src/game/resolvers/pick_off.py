# src/game/resolvers/pick_off.py

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
from src.game.resolvers.base_running import advance_all_runners
from src.game.probabilities import (
    PICKOFF_SUCCESS_PROB,
    PICKOFF_ERROR_PROB,
    PICKOFF_DROP_SHARE,
    STEAL_ON_PICKOFF_MODIFIER,
    SS_OVER_2B_PROB,
)
from src.player.player_in_game import PlayerInGame


def resolve_pickoff(resolver, intent: PickOffIntent, game) -> list[GameEvent]:
    """
    Resolve a pickoff attempt.

    Possible outcomes:
    1. Successful pickoff (runner out)
    2. Failed pickoff (runner safe, no advancement)
    3. Error (runner advances): the pitcher's throw gets away, or the man
       at the bag drops it, and the error goes to whoever it was
    """
    events: list[GameEvent] = []

    base = intent.target_base
    runner = game.bases.runner_on(base)

    if not runner:
        return events

    events.append(PickoffAttemptEvent(base=base, runner=runner, pitcher=intent.pitcher))

    cover = bag_fielder(resolver, game, base)
    success_prob, throw_error_prob, drop_error_prob = adjust_pickoff_success(
        resolver,
        base,
        intent.pitcher,
        game,
        runner.skills["base_running"],
        intent.steal_on,
        cover=cover,
    )
    r = resolver.rng.random()
    if r < success_prob:
        # Successful pickoff - runner out
        resolver.logger.debug(f"Successful pickoff at base {base}")
        events.append(
            PickoffSuccessEvent(base=base, runner=runner, pitcher=intent.pitcher)
        )
        events.append(PutOutEvent(fielder=cover, assist=intent.pitcher))
        events.append(OutRecordedEvent(reason="pickoff", pitcher=intent.pitcher))
        events.append(
            RunnerRemovedEvent(runner=runner, from_base=base, reason="pickoff")
        )

    elif r < success_prob + throw_error_prob + drop_error_prob:
        dropped = r >= success_prob + throw_error_prob
        resolver.logger.debug(f"Pickoff error at base {base}, dropped={dropped}")
        events.append(
            PickoffErrorEvent(
                base=base,
                runner=runner,
                pitcher=intent.pitcher,
                fielder=cover if dropped else intent.pitcher,
            )
        )
        # Advance all runners one base
        events.extend(
            advance_all_runners(
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


def bag_fielder(resolver, game, base: int) -> PlayerInGame:
    """The man who takes a pickoff throw at this base."""
    if base == THIRD:
        return game.pos("3b")
    if base == SECOND:
        if resolver.rng.random() < SS_OVER_2B_PROB:
            return game.pos("ss")
        return game.pos("2b")
    return game.pos("1b")


def adjust_pickoff_success(
    resolver,
    base: int,
    pitcher: PlayerInGame,
    game,
    br_skill=50,
    steal_on=False,
    cover: PlayerInGame | None = None,
):
    """(success, pitcher's throwing error, bag man's drop) chances."""
    success = PICKOFF_SUCCESS_PROB
    resolver.logger.trace(
        f"pickoff success vars, base={base}, pitcher.throws={pitcher.throws}, baserunning={br_skill}"
    )
    if base is FIRST and pitcher.throws[0].lower() == "l":
        success *= 1.1
    if base is THIRD and pitcher.throws[0].lower() == "r":
        success *= 1.1
    success = success * 50 / max(30, br_skill)
    accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
    throw = PICKOFF_ERROR_PROB * (1 - PICKOFF_DROP_SHARE) * 50 / max(30, accuracy)
    if cover is None:
        cover = bag_fielder(resolver, game, base)
    infield = cover.skills["infield"]
    drop = PICKOFF_ERROR_PROB * PICKOFF_DROP_SHARE * 50 / max(30, infield)
    if steal_on:
        success *= STEAL_ON_PICKOFF_MODIFIER
    return success, throw, drop
