# src/game/resolvers/outs.py

from src.game.bases import Bases, FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.error import (
    FieldingErrorEvent,
    ThrowingErrorEvent,
    OutfielderThrowingErrorEvent,
)
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
    FlyOutEvent,
    GroundOutEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.resolvers.base_running import advance_all_runners, advance_batter_to_base
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.resolvers.probabilities import (
    PROB_TAGUP_FROM_SECOND_FLYOUT,
    PROB_TAGUP_FROM_FIRST_FLYOUT,
    BASE_ERROR_RATE,
)


def resolve_fly_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a fly out"""
    fs = FielderSelector(game.rng)
    events: list[GameEvent] = []
    outfielder = fs.select_outfielder(game)
    arm = outfielder.skills["arm"]
    of_skill = outfielder.skills["outfield"]

    tag_from_second, tag_from_first = adjust_tagup_probs(
        resolver, game.inning.outs, game.bases, arm
    )
    runner_on_first = game.bases.runner_on(FIRST)
    runner_on_second = game.bases.runner_on(SECOND)
    runner_on_third = game.bases.runner_on(THIRD)
    if runner_on_second is None:
        second_open = True
    else:
        second_open = False
    if runner_on_third is None:
        third_open = True
    else:
        third_open = False
    if third_open and runner_on_second:
        r = resolver.rng.random()
        if r < tag_from_second:
            second_open = True
            runner_on_third = runner_on_second
            throwing_error_prob = _calculate_throwing_error_probability(
                resolver, of_skill, arm
            )
            if resolver.rng.random() < throwing_error_prob:
                events.append(
                    OutfielderThrowingErrorEvent(
                        fielder=outfielder, runner=runner_on_second
                    )
                )
                # Runner advances an extra base
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner_on_second,
                        pitcher=intent.pitcher,
                        from_base=SECOND,
                        to_base=HOME,
                        reason="Tag up, second to home on error",
                        # rbi_batter=intent.batter, # no RBI scoring on an error
                    )
                )
            else:
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner_on_second,
                        pitcher=intent.pitcher,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="Tag up, second to third",
                        rbi_batter=intent.batter,
                    )
                )

    if second_open and runner_on_first:
        r = resolver.rng.random()
        if r < tag_from_first:
            if runner_on_third:
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner_on_first,
                        pitcher=intent.pitcher,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="Tag up from first to second",
                        rbi_batter=intent.batter,
                    )
                )
            else:
                throwing_error_prob = _calculate_throwing_error_probability(
                    resolver, of_skill, arm
                )
                if resolver.rng.random() < throwing_error_prob:
                    events.append(
                        OutfielderThrowingErrorEvent(
                            fielder=outfielder, runner=runner_on_first
                        )
                    )
                    # Runner advances an extra base
                    events.append(
                        RunnerAdvancedEvent(
                            runner=runner_on_first,
                            pitcher=intent.pitcher,
                            from_base=FIRST,
                            to_base=THIRD,
                            reason="Tag up, first to third on error",
                            # rbi_batter=game.current_batter, # no RBI scoring on an error
                        )
                    )
                else:
                    events.append(
                        RunnerAdvancedEvent(
                            runner=runner_on_first,
                            pitcher=intent.pitcher,
                            from_base=FIRST,
                            to_base=SECOND,
                            reason="Tag up from first",
                            rbi_batter=intent.batter,
                        )
                    )

    events.append(FlyOutEvent(batter=intent.batter))
    events.append(PutOutEvent(outfielder))
    events.append(OutRecordedEvent(reason="fly_out", pitcher=intent.pitcher))
    events.append(PlateAppearanceEndEvent(reason="fly_out", batter=intent.batter))

    return events


def adjust_tagup_probs(
    resolver, outs: int, bases: Bases, arm: int
) -> tuple[float, float]:
    """
    Adjust probabilities that a runner tags up.

    Returns:
        tuple[float, float]: (tag_from_second_prob, tag_from_first_prob)
    """
    tag_from_second = PROB_TAGUP_FROM_SECOND_FLYOUT
    tag_from_first = PROB_TAGUP_FROM_FIRST_FLYOUT
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

    if outs >= 2:
        tag_from_first = 0
        tag_from_second = 0

    return tag_from_second, tag_from_first


def resolve_ground_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a ground out"""
    events: list[GameEvent] = []
    fs = FielderSelector(game.rng)
    # Determine which infielder fields the ball
    fielder = fs.select_infielder(game)

    fielding_skill = fielder.ratings.get(fielder.current_position, 50)

    arm_skill = fielder.skills["arm"]

    # Check if fielder makes an error
    error_prob = _calculate_error_probability(resolver, fielding_skill)
    throwing_error_prob = _calculate_throwing_error_probability(
        resolver, fielding_skill, arm_skill
    )

    r = resolver.rng.random()

    if r < error_prob:
        reason = "fielding_error"
        events.append(FieldingErrorEvent(fielder=fielder, batter=intent.batter))
        events.extend(handle_fielding_error_advancement(resolver, intent, game))
    elif r < error_prob + throwing_error_prob:
        reason = "throwing_error"
        events.append(ThrowingErrorEvent(fielder=fielder, batter=intent.batter))
        events.extend(handle_fielding_error_advancement(resolver, intent, game))
    else:
        # Successful out
        reason = "ground_out"
        events.append(GroundOutEvent(batter=intent.batter))
        if fielder == game.pos("1b"):
            # unassisted 3u
            events.append(PutOutEvent(fielder=game.pos("1b")))
        else:
            events.append(PutOutEvent(fielder=game.pos("1b"), assist=fielder))
        events.append(OutRecordedEvent(reason="ground_out", pitcher=intent.pitcher))
        events.extend(
            advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="ground_out",
            )
        )
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

    return events


def handle_fielding_error_advancement(resolver, intent, game) -> list[GameEvent]:
    # Advance all runners one base
    events: list[GameEvent] = []

    events.extend(
        advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=1,
            reason="fielding_error",
            rbi_batter=intent.batter,
        )
    )

    # Batter to first
    events.extend(
        advance_batter_to_base(intent.batter, intent.pitcher, FIRST, "fielding_error")
    )

    return events


def _calculate_error_probability(resolver, fielding_skill: int) -> float:
    """Calculate probability of fielding error based on skill"""
    # Base error rate around 2-3% for average fielder (skill=50)
    base_error_rate = BASE_ERROR_RATE
    # Scale based on skill (lower skill = higher error rate)
    return base_error_rate * (100 - fielding_skill) / 50


def _calculate_throwing_error_probability(
    resolver, fielding_skill: int, arm_skill: int
) -> float:
    """Calculate probability of throwing error based on arm skill."""
    # Slightly lower base rate than fielding errors
    base_error_rate = BASE_ERROR_RATE * 0.6
    return base_error_rate * (200 - fielding_skill - arm_skill) / 100
