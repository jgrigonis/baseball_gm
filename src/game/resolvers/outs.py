# src/game/resolvers/outs.py

from src.game.bases import Bases, FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.error import (
    FieldingErrorEvent,
    ThrowingErrorEvent,
    OutfielderThrowingErrorEvent,
)
from src.game.events.out import (
    AirDoublePlayEvent,
    PutOutEvent,
    OutRecordedEvent,
    FlyOutEvent,
    GroundOutEvent,
    LineOutEvent,
    fielders_on,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.resolvers.base_running import advance_all_runners, advance_batter_to_base
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.probabilities import (
    PROB_TAGUP_FROM_SECOND_FLYOUT,
    PROB_TAGUP_FROM_FIRST_FLYOUT,
    FLY_DROP_FACTOR,
    FLY_DROP_BATTER_TO_SECOND_PROB,
    LINE_DRIVE_SHARE,
    LINE_DRIVE_INFIELD_SHARE,
    DOUBLED_OFF_RUNNING_PROB,
    DOUBLED_OFF_LEANING_PROB,
    DOUBLED_OFF_OF_RUNNING_PROB,
    TAGUP_OUT_AT_HOME_PROB,
    TAGUP_OUT_AT_THIRD_PROB,
    TAGUP_OUT_AT_SECOND_PROB,
    SS_OVER_2B_PROB,
)
from src.game.resolvers.errors import (
    fielding_error_prob,
    throwing_error_prob,
    fielding_error_chance,
    handle_fielding_error_advancement,
)


def resolve_fly_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a fly out. Some are line drives (LINE_DRIVE_SHARE), and some
    of those are caught by an infielder; a runner off with the pitch can be
    doubled off, and a runner tagging up can be thrown out."""
    if resolver.rng.random() < LINE_DRIVE_SHARE:
        if resolver.rng.random() < LINE_DRIVE_INFIELD_SHARE:
            return _infield_line_out(resolver, intent, game)
        return _outfield_fly(resolver, intent, game, liner=True)
    return _outfield_fly(resolver, intent, game, liner=False)


def _outfield_fly(resolver, intent, game, liner: bool) -> list[GameEvent]:
    fs = FielderSelector(game.rng)
    events: list[GameEvent] = []
    outfielder = fs.select_outfielder(game)
    arm = outfielder.skills["arm"]
    of_skill = outfielder.skills["outfield"]

    # A muffed fly ball: the batter reaches, sometimes all the way to second.
    if resolver.rng.random() < fielding_error_chance(outfielder, FLY_DROP_FACTOR):
        return _dropped_fly_ball(resolver, intent, game, outfielder)

    # A liner to the outfield with a runner going: he can't get back.
    if liner and game.inning.outs < 2:
        for base in (THIRD, SECOND, FIRST):
            if (
                runner_going(game, base)
                and resolver.rng.random() < DOUBLED_OFF_OF_RUNNING_PROB
            ):
                return _doubled_off(resolver, intent, game, outfielder, base)

    tag_from_second, tag_from_first = adjust_tagup_probs(
        resolver, game.inning.outs, game.bases, arm
    )
    runner_on_first = game.bases.runner_on(FIRST)
    runner_on_second = game.bases.runner_on(SECOND)
    runner_on_third = game.bases.runner_on(THIRD)
    second_open = runner_on_second is None
    third_open = runner_on_third is None
    if third_open and runner_on_second:
        r = resolver.rng.random()
        if r < tag_from_second:
            if _thrown_out_tagging(resolver, outfielder, runner_on_second, THIRD):
                return events + _tag_up_double_play(
                    resolver, intent, game, outfielder, runner_on_second, SECOND
                )
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
            if not runner_on_third and _thrown_out_tagging(
                resolver, outfielder, runner_on_first, SECOND
            ):
                return events + _tag_up_double_play(
                    resolver, intent, game, outfielder, runner_on_first, FIRST
                )
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

    reason = "line_out" if liner else "fly_out"
    events.append(
        LineOutEvent(batter=intent.batter)
        if liner
        else FlyOutEvent(batter=intent.batter)
    )
    events.append(PutOutEvent(outfielder))
    events.append(OutRecordedEvent(reason=reason, pitcher=intent.pitcher))
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

    return events


def runner_going(game, base: int) -> bool:
    """Was the runner on this base off with the pitch (a steal or a hit and
    run)?"""
    if game.bases.runner_on(base) is None:
        return False
    sit = getattr(game, "situation", None)
    if sit is None:
        return False
    if sit.hit_and_run:
        return True
    if sit.steal_attempt == base:
        return True
    return base in (sit.double_steal_attempt or ())


def _skill(player, name: str) -> float:
    skills = getattr(player, "skills", None)
    try:
        return skills[name]
    except KeyError, TypeError:
        return 50


def _careless(runner) -> float:
    return 50 / max(30, _skill(runner, "base_running"))


def _infield_line_out(resolver, intent, game) -> list[GameEvent]:
    """A liner snared by an infielder (or the pitcher). Runners off with
    the pitch are usually doubled off; one caught leaning sometimes is."""
    fielder = FielderSelector(game.rng).select_infielder(game)
    if game.inning.outs < 2:
        for base in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(base)
            if runner is None:
                continue
            if runner_going(game, base):
                p = DOUBLED_OFF_RUNNING_PROB
            else:
                p = DOUBLED_OFF_LEANING_PROB * _careless(runner)
            if resolver.rng.random() < p:
                return _doubled_off(resolver, intent, game, fielder, base)
    return [
        LineOutEvent(batter=intent.batter),
        PutOutEvent(fielder),
        OutRecordedEvent(reason="line_out", pitcher=intent.pitcher),
        PlateAppearanceEndEvent(reason="line_out", batter=intent.batter),
    ]


def _bag_man(resolver, game, base: int, fielder):
    """Who takes the throw to double a runner off this base. The fielder
    who caught it steps on the bag himself when it's his."""
    own = {FIRST: ("1b",), SECOND: ("2b", "ss"), THIRD: ("3b",)}[base]
    if fielder.current_position in own:
        return fielder
    if base == SECOND:
        return (
            game.pos("ss")
            if resolver.rng.random() < SS_OVER_2B_PROB
            else game.pos("2b")
        )
    return game.pos(own[0])


def _doubled_off(resolver, intent, game, fielder, base) -> list[GameEvent]:
    """The catch, then the throw back to the runner's base before he can
    get back: a line drive double play."""
    runner = game.bases.runner_on(base)
    cover = _bag_man(resolver, game, base, fielder)
    second_out = (
        PutOutEvent(fielder) if cover is fielder else PutOutEvent(cover, fielder)
    )
    return [
        AirDoublePlayEvent(
            batter=intent.batter,
            runner=runner,
            base=base,
            fielders=fielders_on([PutOutEvent(fielder), second_out]),
            kind="line",
        ),
        PutOutEvent(fielder),
        OutRecordedEvent(reason="double_play", pitcher=intent.pitcher),
        second_out,
        OutRecordedEvent(reason="double_play", pitcher=intent.pitcher),
        RunnerRemovedEvent(runner=runner, from_base=base, reason="doubled_off"),
        PlateAppearanceEndEvent(reason="line_drive_double_play", batter=intent.batter),
    ]


def _thrown_out_tagging(resolver, outfielder, runner, to_base) -> bool:
    """A runner tagging up on a fly ball beaten by the throw: more often
    against a strong arm, less often for a fast, smart runner."""
    base_prob = {
        SECOND: TAGUP_OUT_AT_SECOND_PROB,
        THIRD: TAGUP_OUT_AT_THIRD_PROB,
        HOME: TAGUP_OUT_AT_HOME_PROB,
    }[to_base]
    arm = max(30, _skill(outfielder, "arm"))
    legs = max(30, (_skill(runner, "speed") + _skill(runner, "base_running")) / 2)
    return resolver.rng.random() < base_prob * (arm / 55) * (55 / legs)


def _tag_up_double_play(
    resolver, intent, game, outfielder, runner, from_base
) -> list[GameEvent]:
    """The fly ball is caught and the tagging runner is thrown out at the
    next base. Nobody else moves."""
    to_base = from_base + 1
    if to_base == HOME:
        cover = game.pos("c")
    elif to_base == THIRD:
        cover = game.pos("3b")
    else:
        cover = (
            game.pos("ss")
            if resolver.rng.random() < SS_OVER_2B_PROB
            else game.pos("2b")
        )
    throw = PutOutEvent(cover, outfielder)
    return [
        AirDoublePlayEvent(
            batter=intent.batter,
            runner=runner,
            base=to_base,
            fielders=fielders_on([PutOutEvent(outfielder), throw]),
            kind="fly",
        ),
        PutOutEvent(outfielder),
        OutRecordedEvent(reason="double_play", pitcher=intent.pitcher),
        throw,
        OutRecordedEvent(reason="double_play", pitcher=intent.pitcher),
        RunnerRemovedEvent(runner=runner, from_base=from_base, reason="tag_up_out"),
        PlateAppearanceEndEvent(reason="fly_double_play", batter=intent.batter),
    ]


def _dropped_fly_ball(resolver, intent, game, outfielder) -> list[GameEvent]:
    bases = 2 if resolver.rng.random() < FLY_DROP_BATTER_TO_SECOND_PROB else 1
    events: list[GameEvent] = [
        FieldingErrorEvent(fielder=outfielder, batter=intent.batter)
    ]
    events.extend(
        advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=bases,
            reason="dropped_fly_ball",
        )
    )
    events.extend(
        advance_batter_to_base(
            intent.batter, intent.pitcher, FIRST + bases - 1, "dropped_fly_ball"
        )
    )
    events.append(
        PlateAppearanceEndEvent(reason="fly_ball_error", batter=intent.batter)
    )
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
        # Fielding error
        reason = "fielding_error"
        events.append(FieldingErrorEvent(fielder=fielder, batter=intent.batter))
        events.extend(handle_fielding_error_advancement(resolver, intent, game))
    elif r < error_prob + throwing_error_prob:
        # Throwing error
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
        # Only advance runners who are NOT in a force situation
        # (i.e., runner on 2nd or 3rd can advance on a ground out, but runner on 1st cannot
        # if 1st is occupied — they'd have been a fielder's choice or DP instead)
        force_bases = []
        non_force_bases = []
        for base in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(base)
            if not runner:
                continue
            # A runner is in a force situation if all bases behind them are occupied
            if base == FIRST:
                force_bases.append(base)  # always forced on a ground out
            elif base == SECOND and game.bases.runner_on(FIRST):
                force_bases.append(base)
            elif (
                base == THIRD
                and game.bases.runner_on(SECOND)
                and game.bases.runner_on(FIRST)
            ):
                force_bases.append(base)
            else:
                non_force_bases.append(base)

        # Forced runners don't advance — they'd have been a FC/DP (that path handles it)
        # Non-forced runners advance probabilistically
        events.extend(
            advance_all_runners(
                game, tuple(non_force_bases), advancement=1, reason="ground_out"
            )
        )
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

    return events


def _calculate_error_probability(resolver, fielding_skill: int) -> float:
    """Calculate probability of fielding error based on skill"""
    return fielding_error_prob(fielding_skill)


def _calculate_throwing_error_probability(
    resolver, fielding_skill: int, arm_skill: int
) -> float:
    """Calculate probability of throwing error based on arm skill."""
    return throwing_error_prob(fielding_skill, arm_skill)
