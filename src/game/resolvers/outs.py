# src/game/resolvers/outs.py

from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.error import FieldingErrorEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
    FlyOutEvent,
    GroundOutEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent


def resolve_fly_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a fly out"""
    events: list[GameEvent] = []
    lf_arm = game.pos("lf").skills["arm"]
    cf_arm = game.pos("cf").skills["arm"]
    rf_arm = game.pos("rf").skills["arm"]
    arm = resolver.rng.choice([lf_arm, cf_arm, rf_arm])

    tag_from_second, tag_from_first = adjust_tagup_probs(resolver, game.bases, arm)
    if game.bases.runner_on(SECOND) is None:
        second_open = True
    else:
        second_open = False
    if game.bases.runner_on(THIRD) is None and game.bases.runner_on(SECOND):
        r = resolver.rng.random()
        if r < tag_from_second:
            second_open = True
            events.append(
                RunnerAdvancedEvent(
                    game.bases.runner_on(SECOND),
                    pitcher=intent.pitcher,
                    from_base=SECOND,
                    to_base=THIRD,
                    reason="Tag up",
                    rbi_batter=game.current_batter,
                )
            )

    if second_open and game.bases.runner_on(FIRST):
        r = resolver.rng.random()
        if r < tag_from_first:
            events.append(
                RunnerAdvancedEvent(
                    game.bases.runner_on(FIRST),
                    pitcher=intent.pitcher,
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="Tag up",
                    rbi_batter=game.current_batter,
                )
            )

    events.append(FlyOutEvent(batter=intent.batter))
    events.append(PutOutEvent(resolver._select_outfielder(game)))
    events.append(OutRecordedEvent(reason="fly_out", pitcher=intent.pitcher))
    events.append(PlateAppearanceEndEvent(reason="fly_out", batter=intent.batter))

    return events


def adjust_tagup_probs(resolver, bases: Bases, arm: int) -> tuple[float, float]:
    """
    Adjust probabilities that a runner tags up.

    Returns:
        tuple[float, float]: (tag_from_second_prob, tag_from_first_prob)
    """
    tag_from_second = resolver.PROB_TAGUP_FROM_SECOND_FLYOUT
    tag_from_first = resolver.PROB_TAGUP_FROM_FIRST_FLYOUT
    if bases.runner_on(THIRD):
        tag_from_second = 0
    elif bases.runner_on(SECOND):
        # adjust based on random outfielder arm and scond base runner speed and baserunning skill
        speed = bases.runner_on(SECOND).skills["speed"]
        br_skill = bases.runner_on(SECOND).skills["base_running"]
        tag_from_second = tag_from_second * (speed + br_skill) / (2 * arm)

    if bases.runner_on(FIRST) and bases.one_man_on:
        speed = bases.runner_on(FIRST).skills["speed"]
        br_skill = bases.runner_on(FIRST).skills["base_running"]
        tag_from_first = tag_from_first * (speed + br_skill) / (2 * arm)

    return tag_from_second, tag_from_first


def resolve_ground_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a ground out"""
    events: list[GameEvent] = []

    # Determine which infielder fields the ball
    fielder = resolver._select_infielder(game)
    fielding_skill = fielder.skills["infield"]

    # Check if fielder makes an error
    error_prob = _calculate_error_probability(resolver, fielding_skill)

    if resolver.rng.random() < error_prob:
        reason = "fielding_error"
        events.append(FieldingErrorEvent(fielder=fielder, batter=intent.batter))
        events.extend(resolver._handle_fielding_error_advancement(intent, game))
    else:
        # Successful out
        reason = "ground_out"
        events.append(GroundOutEvent(batter=intent.batter))
        events.append(PutOutEvent(fielder=game.pos("1b"), assist=fielder))
        events.append(OutRecordedEvent(reason="ground_out", pitcher=intent.pitcher))
        events.extend(
            resolver._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="ground_out",
            )
        )
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

    return events


def _calculate_error_probability(resolver, fielding_skill: int) -> float:
    """Calculate probability of fielding error based on skill"""
    # Base error rate around 2-3% for average fielder (skill=50)
    base_error_rate = resolver.BASE_ERROR_RATE
    # Scale based on skill (lower skill = higher error rate)
    return base_error_rate * (100 - fielding_skill) / 50
