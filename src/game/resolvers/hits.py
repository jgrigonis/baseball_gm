# src/game/resolvers/hits.py

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.hits import SingleEvent, DoubleEvent, TripleEvent, HomeRunEvent
from src.game.events.out import OutRecordedEvent, PutOutEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent


def resolve_single(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a single with varied base advancement possibilities:
    - Runner on 2nd: usually scores, sometimes holds at 3rd
    - Runner on 1st: usually to 3rd, sometimes to 2nd, rarely scores
    - Batter always to 1st
    """
    events: list[GameEvent] = []
    events.append(SingleEvent(batter=intent.batter, pitcher=intent.pitcher))

    # Select outfielder who fields the ball
    fielder = resolver._select_outfielder(game)
    arm_strength = fielder.skills["arm"]

    # Handle runner on third (always scores on single)
    if game.bases.runner_on(THIRD):
        events.append(
            RunnerAdvancedEvent(
                runner=game.bases.runner_on(THIRD),
                from_base=THIRD,
                to_base=HOME,
                reason="single",
                rbi_batter=intent.batter,
                pitcher=intent.pitcher,
            )
        )

    held_at_third = False
    # Handle runner on second
    if game.bases.runner_on(SECOND):
        runner = game.bases.runner_on(SECOND)
        speed = runner.skills["speed"]
        baserunning = runner.skills["base_running"]

        # Base probability of scoring from second on a single: 60%
        base_score_prob = resolver.SCORE_FROM_SECOND_ON_SINGLE
        arm_factor = 50 / arm_strength  # Strong arm reduces scoring
        runner_factor = (speed + baserunning) / 100

        score_prob = base_score_prob * runner_factor * arm_factor

        if resolver.rng.random() < score_prob:
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=SECOND,
                    to_base=HOME,
                    reason="single",
                    rbi_batter=intent.batter,
                    pitcher=intent.pitcher,
                )
            )
        else:
            held_at_third = True
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=SECOND,
                    to_base=THIRD,
                    reason="single",
                    pitcher=intent.pitcher,
                )
            )

    # Handle runner on first
    if game.bases.runner_on(FIRST):
        runner = game.bases.runner_on(FIRST)
        speed = runner.skills["speed"]
        baserunning = runner.skills["base_running"]

        # Base probability of first to third on a single: 35%
        base_f2t_prob = resolver.FIRST_TO_THIRD_ON_SINGLE
        base_fth_prob = resolver.FIRST_TO_HOME_ON_SINGLE
        arm_factor = 50 / arm_strength  # Strong arm reduces advancement
        runner_factor = (speed + baserunning) / 100

        first_to_third_prob = base_f2t_prob * runner_factor * arm_factor

        if resolver.rng.random() < base_fth_prob and not held_at_third:
            # First to home
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=HOME,
                    reason="single",
                    rbi_batter=intent.batter,
                    pitcher=intent.pitcher,
                )
            )
        elif resolver.rng.random() < first_to_third_prob and not held_at_third:
            # First to third
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=THIRD,
                    reason="single",
                    pitcher=intent.pitcher,
                )
            )
        else:
            # First to second
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="single",
                    pitcher=intent.pitcher,
                )
            )

    # Batter to first
    events.append(
        resolver._advance_batter_to_base(intent.batter, intent.pitcher, FIRST, "single")
    )

    events.append(PlateAppearanceEndEvent(reason="single", batter=intent.batter))

    return events


def resolve_double(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a double:
    - All runners advance two bases by default
    - Batter to second
    - Plate appearance ends
    Also, sometimes they can be thrown out.
    """
    events: list[GameEvent] = []

    events.append(DoubleEvent(batter=intent.batter, pitcher=intent.pitcher))

    # Select which outfielder fields the ball
    fielder = resolver._select_outfielder(game)
    arm_strength = fielder.skills["arm"]

    if game.bases.runner_on(FIRST):
        speed = game.bases.runner_on(FIRST).skills["speed"]
        skill = game.bases.runner_on(FIRST).skills["base_running"]
        # Advance runners on second and third two bases
        events.extend(
            resolver._advance_all_runners(
                game,
                (THIRD, SECOND),
                advancement=2,
                reason="double",
                rbi_batter=intent.batter,
            )
        )
        # Calculate scoring probability based on arm strength
        base_score_prob = resolver.SCORE_FROM_FIRST_ON_DOUBLE
        arm_factor = 50 / arm_strength  # Strong arm reduces scoring
        runner_factor = (speed + skill) / 100
        score_prob = base_score_prob * runner_factor * arm_factor

        if resolver.rng.random() < score_prob:
            events.append(
                RunnerAdvancedEvent(
                    runner=game.bases.runner_on(FIRST),
                    from_base=FIRST,
                    to_base=HOME,
                    reason="double",
                    rbi_batter=intent.batter,
                    pitcher=intent.pitcher,
                )
            )
        else:
            # Check if runner is thrown out trying to score
            throw_out_prob = resolver._calculate_throw_out_probability(
                arm_strength, speed, skill
            )
            if resolver.rng.random() < throw_out_prob:
                events.extend(
                    [
                        PutOutEvent(fielder=game.pos("c"), assist=fielder),
                        OutRecordedEvent(
                            reason="thrown_out_at_home", pitcher=intent.pitcher
                        ),
                        RunnerRemovedEvent(
                            runner=game.bases.runner_on(FIRST),
                            from_base=FIRST,
                            reason="thrown_out_at_home",
                        ),
                    ]
                )
            else:
                events.append(
                    RunnerAdvancedEvent(
                        runner=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        to_base=THIRD,
                        reason="double",
                        pitcher=intent.pitcher,
                    )
                )

    else:
        # Advance all runners two bases
        events.extend(
            resolver._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=2,
                reason="double",
                rbi_batter=intent.batter,
            )
        )

    # Batter to second
    events.append(
        resolver._advance_batter_to_base(
            intent.batter, intent.pitcher, SECOND, "double"
        )
    )

    events.append(PlateAppearanceEndEvent(reason="double", batter=intent.batter))

    return events

def resolve_triple(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a triple:
    - All runners score by default
    - Batter to third
    - Plate appearance ends
    """
    events: list[GameEvent] = []

    events.append(TripleEvent(batter=intent.batter, pitcher=intent.pitcher))

    # All runners score (advancement to HOME)
    events.extend(
        resolver._advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=HOME,  # Will be capped at HOME
            reason="triple",
            rbi_batter=intent.batter,
        )
    )

    # Batter to third
    events.append(
        resolver._advance_batter_to_base(intent.batter, intent.pitcher, THIRD, "triple")
    )

    events.append(PlateAppearanceEndEvent(reason="triple", batter=intent.batter))

    return events



def resolve_home_run(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a home run.

    Score all the runners on base.
    Score the batter.
    """
    events: list[GameEvent] = []

    events.append(HomeRunEvent(batter=intent.batter, pitcher=intent.pitcher))

    # Score all runners
    events.extend(
        resolver._advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=HOME,  # Will be capped at HOME
            reason="home_run",
            rbi_batter=intent.batter,
        )
    )

    # Batter scores
    events.append(
        RunnerAdvancedEvent(
            runner=intent.batter,
            from_base=None,
            to_base=HOME,
            reason="home_run",
            rbi_batter=intent.batter,
            pitcher=intent.pitcher,
        )
    )

    events.append(PlateAppearanceEndEvent(reason="home_run", batter=intent.batter))

    return events
