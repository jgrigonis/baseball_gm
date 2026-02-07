# src/game/resolvers/steal.py
from typing import List

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.intents.pitch import PitchIntent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.steal import (
    StealAttemptEvent,
    StolenBaseEvent,
    CaughtStealingEvent,
    DoubleStealAttemptEvent,
)


def resolve_steal_attempt(
    resolver, from_base: int, intent: PitchIntent, game
) -> List[GameEvent]:
    """
    Resolve a single steal attempt.

    Outcomes:
    - Successful steal
    - Caught stealing
    """
    events = []
    runner = game.bases.runner_on(from_base)
    to_base = from_base + 1

    if not runner:
        return events

    events.append(
        StealAttemptEvent(runner=runner, from_base=from_base, to_base=to_base)
    )

    arm = game.pos("c").skills["arm"]

    if to_base == SECOND:
        success_prob = resolver.STEAL_SECOND_SUCCESS_PROB

    elif to_base == THIRD:
        success_prob = resolver.STEAL_THIRD_SUCCESS_PROB
    elif to_base == HOME:
        success_prob = resolver.STEAL_HOME_SUCCESS_PROB
        arm = 50  # We just set this to average as it's not relevant
    else:
        success_prob = 0.50

    success_prob = adjust_steal_prob(
        resolver,
        success_prob,
        game.bases.runner_on(from_base).skills["speed"],
        game.bases.runner_on(from_base).skills["base_running"],
        arm,
        game.pos("c").skills["catching"],
    )

    if resolver.rng.random() < success_prob:
        # Successful steal
        resolver.logger.debug(f"Successful steal: {from_base} -> {to_base}")
        events.append(
            StolenBaseEvent(
                runner=runner,
                from_base=from_base,
                to_base=to_base,
                catcher=game.pos("c"),
            )
        )
        events.append(
            RunnerAdvancedEvent(
                runner=runner,
                from_base=from_base,
                to_base=to_base,
                reason="stolen_base",
                pitcher=intent.pitcher,
            )
        )
    else:
        # Caught stealing
        resolver.logger.debug(f"Caught stealing: {from_base} -> {to_base}")
        events.append(
            CaughtStealingEvent(
                runner=runner,
                from_base=from_base,
                to_base=to_base,
                catcher=game.pos("c"),
            )
        )
        assist = game.pos("c")
        if to_base == SECOND:
            if resolver.rng.random() < 0.55:
                fielder = game.pos("ss")
            else:
                fielder = game.pos("2b")
        elif to_base == THIRD:
            fielder = game.pos("3b")
        else:
            fielder = game.pos("c")
            assist = game.pos("p")
        events.append(PutOutEvent(fielder=fielder, assist=assist))
        events.append(
            OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
        )
        events.append(
            RunnerRemovedEvent(
                runner=runner, from_base=from_base, reason="caught_stealing"
            )
        )

    return events


def adjust_steal_prob(
    resolver, prob, run_speed=50, base_running=50, catcher_arm=50, catching_skill=50
) -> float:
    return (run_speed + base_running) / max(1, (catcher_arm + catching_skill)) * prob


def resolve_double_steal(
    resolver, from_bases: List[int], intent: PitchIntent, game
) -> List[GameEvent]:
    """
    Resolve a double steal attempt.

    Args:
        from_bases: Bases runners are currently on (e.g., [1, 2])
    """
    events = []

    # CRITICAL: Sort in reverse order (lead runner first)
    # This ensures we advance 2nd→3rd BEFORE 1st→2nd
    sorted_bases = sorted(from_bases, reverse=True)

    # Build steal attempt info (in reverse order)
    steal_attempts = [
        (from_base, from_base + 1, game.bases.runner_on(from_base))
        for from_base in sorted_bases
    ]

    # Record all attempts (order doesn't matter for logging)
    for from_base, to_base, runner in steal_attempts:
        events.append(
            StealAttemptEvent(runner=runner, from_base=from_base, to_base=to_base)
        )

    events.append(DoubleStealAttemptEvent(bases=from_bases))

    # Check if this is 1st and 3rd scenario
    is_first_and_third = FIRST in from_bases and THIRD in from_bases

    if is_first_and_third:
        # Reset to base probabilities and apply modifiers
        resolver.first_and_third_choice.reset()
        _modify_first_and_third_probs(resolver, game)
        result = resolver.first_and_third_choice.choose()
        # # 1st and 3rd special handling
        first_attempt = next(a for a in steal_attempts if a[0] == FIRST)
        third_attempt = next(a for a in steal_attempts if a[0] == THIRD)

        if result == "both_safe":
            # Both safe - ADVANCE IN REVERSE ORDER
            # Third → Home first, then First → Second
            from_base, to_base, runner = third_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )

            from_base, to_base, runner = first_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )
        elif result == "first_advances_only":
            # Only runner on 1st steals (runner on 3rd holds)
            from_base, to_base, runner = first_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )
        elif result == "first_out_third_scores":
            # Runner on 1st out, runner on 3rd scores
            from_base, to_base, runner = third_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )

            from_base, to_base, runner = first_attempt
            events.append(
                CaughtStealingEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            if resolver.rng.random() < 0.55:
                events.append(
                    PutOutEvent(
                        game.pos("ss"),
                        game.pos("c"),
                    )
                )
            else:
                events.append(
                    PutOutEvent(
                        game.pos("2b"),
                        game.pos("c"),
                    )
                )
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )
        elif result == "third_out_first_advances":
            # Runner on 3rd caught, runner on 1st safe
            from_base, to_base, runner = third_attempt
            events.append(
                CaughtStealingEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(PutOutEvent(game.pos("c"), game.pos("p")))
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )

            from_base, to_base, runner = first_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )
        elif result == "both_out":
            # Both out
            if resolver.rng.random() < 0.55:
                events.append(
                    PutOutEvent(
                        game.pos("ss"),
                        game.pos("c"),
                    )
                )
                events.append(
                    PutOutEvent(
                        game.pos("c"),
                        game.pos("ss"),
                    )
                )
            else:
                events.append(
                    PutOutEvent(
                        game.pos("2b"),
                        game.pos("c"),
                    )
                )
                events.append(
                    PutOutEvent(
                        game.pos("c"),
                        game.pos("2b"),
                    )
                )
            for from_base, to_base, runner in steal_attempts:
                events.append(
                    CaughtStealingEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        catcher=game.pos("c"),
                    )
                )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner,
                        from_base=from_base,
                        reason="caught_stealing",
                    )
                )
        else:
            raise RuntimeError(f"Unknown result={result} first_and_third_probs")

    else:
        # Reset to base probabilities and apply modifiers
        resolver.double_steal_choice.reset()
        _modify_double_steal_probs(resolver, game)
        result = resolver.double_steal_choice.choose()

        # Standard double steal (1st/2nd or 2nd/3rd)
        # steal_attempts is already sorted in reverse order (lead runner first)
        if result == "both_safe":
            # Both safe - process in order (lead runner first)
            for from_base, to_base, runner in steal_attempts:
                events.append(
                    StolenBaseEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        catcher=game.pos("c"),
                    )
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )
        elif result == "lead_out_trail_safe":
            # Validate: ensure we have exactly 2 runners
            if len(steal_attempts) != 2:
                raise RuntimeError(
                    f"lead_out_trail_safe requires exactly 2 runners, got {len(steal_attempts)}"
                )

            # Lead runner out, trail runner safe
            lead_attempt = steal_attempts[0]  # First in list (highest base)
            trail_attempt = steal_attempts[1]  # Second in list (lowest base)

            from_base, to_base, runner = lead_attempt
            events.append(
                CaughtStealingEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            if to_base == HOME:
                events.append(PutOutEvent(game.pos("c"), game.pos("p")))
            elif to_base == THIRD:
                events.append(
                    PutOutEvent(
                        game.pos("3b"),
                        game.pos("c"),
                    )
                )
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )

            from_base, to_base, runner = trail_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )
        elif result == "lead_safe_trail_out":
            # Validate: ensure we have exactly 2 runners
            if len(steal_attempts) != 2:
                raise RuntimeError(
                    f"lead_safe_trail_out requires exactly 2 runners, got {len(steal_attempts)}"
                )

            # Trail runner out, lead runner safe
            lead_attempt = steal_attempts[0]
            trail_attempt = steal_attempts[1]

            # Lead runner advances first (to clear the base)
            from_base, to_base, runner = lead_attempt
            events.append(
                StolenBaseEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )

            from_base, to_base, runner = trail_attempt
            if to_base == SECOND:
                if resolver.rng.random() < 0.55:
                    events.append(
                        PutOutEvent(
                            game.pos("ss"),
                            game.pos("c"),
                        )
                    )
                else:
                    events.append(
                        PutOutEvent(
                            game.pos("2b"),
                            game.pos("c"),
                        )
                    )
            elif to_base == THIRD:
                events.append(
                    PutOutEvent(
                        game.pos("3b"),
                        game.pos("c"),
                    )
                )
            events.append(
                CaughtStealingEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    catcher=game.pos("c"),
                )
            )
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )

        elif result == "both_out":
            # Both out - order doesn't matter
            for from_base, to_base, runner in steal_attempts:
                # TODO this isn't quite right, we are assuming the catcher threw out both
                # If the double steal is 2nd and third, this is wrong.
                if to_base == SECOND:
                    if resolver.rng.random() < 0.55:
                        events.append(
                            PutOutEvent(
                                game.pos("ss"),
                                game.pos("c"),
                            )
                        )
                    else:
                        events.append(
                            PutOutEvent(
                                game.pos("2b"),
                                game.pos("c"),
                            )
                        )
                elif to_base == THIRD:
                    events.append(
                        PutOutEvent(
                            game.pos("3b"),
                            game.pos("c"),
                        )
                    )
                elif to_base == HOME:
                    events.append(PutOutEvent(game.pos("c"), game.pos("p")))
                events.append(
                    CaughtStealingEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        catcher=game.pos("c"),
                    )
                )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner,
                        from_base=from_base,
                        reason="caught_stealing",
                    )
                )
        else:
            raise RuntimeError(f"Unknown result={result} double_steal_probs")

    return events


def _modify_first_and_third_probs(resolver, game):
    """
    Apply modifiers for first-and-third double steal.

    BEFORE: Direct manipulation of resolver.first_and_third_probs dict
    AFTER: Use WeightedChoice methods
    """
    speed1 = game.bases.runner_on(FIRST).skills["speed"]
    br1 = game.bases.runner_on(FIRST).skills["base_running"]
    speed3 = game.bases.runner_on(THIRD).skills["speed"]
    br3 = game.bases.runner_on(THIRD).skills["base_running"]
    arm = game.pos("c").skills["arm"]
    arm2 = game.pos("2b").skills["arm"]

    # Calculate skill factor
    runner_factor = (speed1 + br1 + speed3 + br3) / 200
    defense_factor = 50 / arm
    defense_factor2 = 50 / arm2

    # Apply multipliers
    resolver.first_and_third_choice.multiply(
        "both_safe", runner_factor * defense_factor
    )
    resolver.first_and_third_choice.multiply(
        "first_advances_only", runner_factor * defense_factor
    )
    resolver.first_and_third_choice.multiply(
        "first_out_third_scores", runner_factor * defense_factor * defense_factor2
    )
    resolver.first_and_third_choice.multiply(
        "third_out_first_advances", runner_factor * defense_factor * defense_factor2
    )

    # Inverse multiplier for both_out
    both_out_factor = (200 / (speed1 + br1 + speed3 + br3)) * (arm / 50) * (arm2 / 50)
    resolver.first_and_third_choice.multiply("both_out", both_out_factor)


def _modify_double_steal_probs(resolver, game):
    """
    Apply modifiers for standard double steal.

    BEFORE: Direct manipulation of resolver.double_steal_probs dict
    AFTER: Use WeightedChoice methods
    """
    if game.bases.runner_on(FIRST):
        runner1 = game.bases.runner_on(FIRST)
        runner2 = game.bases.runner_on(SECOND)
        arm2 = game.pos("3b").skills["arm"]
    else:
        runner1 = game.bases.runner_on(SECOND)
        runner2 = game.bases.runner_on(THIRD)
        arm2 = None

    speed1 = runner1.skills["speed"]
    br1 = runner1.skills["base_running"]
    speed2 = runner2.skills["speed"]
    br2 = runner2.skills["base_running"]
    arm = game.pos("c").skills["arm"]
    catcher = game.pos("c").skills["catching"]

    runner_factor = (speed1 + br1 + speed2 + br2) / 200
    defense_factor = 50 / arm

    resolver.double_steal_choice.multiply("both_safe", runner_factor * defense_factor)

    if arm2:
        both_out_factor = (
            (200 / (speed1 + br1 + speed2 + br2)) * (arm / 50) * (arm2 / 50)
        )
    else:
        both_out_factor = (
            (200 / (speed1 + br1 + speed2 + br2)) * (arm / 50) * (catcher / 50)
        )

    resolver.double_steal_choice.multiply("both_out", both_out_factor)
