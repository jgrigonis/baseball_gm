# src/game/resolvers/double_play.py

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.double_play import DoublePlayEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
    fielders_on,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.resolvers.base_running import advance_all_runners
from src.game.resolvers.base_running import advance_batter_to_base
from src.game.resolvers.errors import (
    everyone_safe_on_error,
    fielding_error_chance,
    force_play_error,
    throwing_error_chance,
)
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.events.error import FieldingErrorEvent, ThrowingErrorEvent
from src.game.probabilities import (
    DP_FIELD_FACTOR,
    DP_FEED_FACTOR,
    DP_PIVOT_DROP_FACTOR,
    DP_RELAY_FACTOR,
    DP_RELAY_DROP_FACTOR,
)


def resolve_double_play(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a double play:
    - Default runner on first is out via force
    - And batter/runner is out

    - Other runners could advance and potentially score

    - If no runner on first, another runner must be put out
    - plus the batter/runner or another runner

    - There must be two outs.

    - Plate appearance ends
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runners=True)

    events: list[GameEvent] = []

    if game.bases.runner_on(FIRST):
        putouts = _choose_double_play(resolver, game)
    elif game.bases.runner_on(THIRD):
        putouts = _3to1_double_play(resolver, game)
    else:
        putouts = _2to1_double_play(resolver, game)

    error_events = _double_play_error(resolver, intent, game, putouts)
    if error_events:
        return error_events

    events.append(
        DoublePlayEvent(
            batter=intent.batter,
            pitcher=intent.pitcher,
            fielders=fielders_on(putouts),
        )
    )
    events.extend(putouts)

    if game.bases.runner_on(FIRST):
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(FIRST),
                from_base=FIRST,
                reason="double_play",
            )
        )
        if game.inning.outs + 2 < 3:  # if the inning is not over, advance the runners
            events.extend(
                advance_all_runners(
                    game,
                    (THIRD, SECOND),
                    advancement=1,
                    reason="double_play",
                )
            )

    # No runner was on first, but we still need a double play
    # try third next.
    elif game.bases.runner_on(THIRD):
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(THIRD),
                from_base=THIRD,
                reason="double_play",
            )
        )
        if game.bases.runner_on(SECOND) and game.bases.runner_on(FIRST):
            runner = game.bases.runner_on(SECOND)
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=SECOND,
                    to_base=THIRD,
                    reason="fielders_choice",
                    pitcher=intent.pitcher,
                )
            )
            runner = game.bases.runner_on(FIRST)
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="fielders_choice",
                    pitcher=intent.pitcher,
                )
            )
        elif game.bases.runner_on(SECOND):
            r = resolver.rng.random()
            if r < 0.67:
                runner = game.bases.runner_on(SECOND)
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )
        elif game.bases.runner_on(FIRST):
            runner = game.bases.runner_on(FIRST)
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="fielders_choice",
                    pitcher=intent.pitcher,
                )
            )
    else:
        # must be a runner on second.
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(SECOND),
                from_base=SECOND,
                reason="double_play",
            )
        )
        if game.bases.runner_on(FIRST):
            runner = game.bases.runner_on(FIRST)
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="fielders_choice",
                    pitcher=intent.pitcher,
                )
            )

    events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))
    events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))
    events.append(PlateAppearanceEndEvent(reason="double_play", batter=intent.batter))

    return events


def _double_play_error(resolver, intent, game, putouts) -> list[GameEvent]:
    """
    Double plays can break down. Returns the events for a botched double
    play, or [] when both outs are made.

    Stage 1, the lead out: the fielder boots the grounder, the feed to the
    bag is bad, or the man covering drops it. Nobody is out, the batter
    reaches on the error and every runner moves up.

    Stage 2, the relay to first: the lead out is made, but the first
    baseman drops the throw (batter safe at first) or the relay sails
    away (batter takes second, runners take an extra base). Per the
    scoring rules a merely late or off-line relay is not an error, so
    only the throws bad enough to cost an extra base count here.
    """
    first, second = putouts[0], putouts[1]

    error = force_play_error(
        resolver, first, DP_FIELD_FACTOR, DP_FEED_FACTOR, DP_PIVOT_DROP_FACTOR
    )
    if error:
        return everyone_safe_on_error(
            resolver, intent, game, error, reason="double_play_error"
        )

    # Only a relay throw to first can be botched for a lone extra out.
    relay_to_first = (
        second.assist is not None
        and second.assist is not second.fielder
        and (second.fielder is game.pos("1b") or second.fielder is game.pos("p"))
    )
    if not relay_to_first:
        return []

    p_wild = throwing_error_chance(second.assist, DP_RELAY_FACTOR)
    p_drop = fielding_error_chance(second.fielder, DP_RELAY_DROP_FACTOR)
    r = resolver.rng.random()
    if r < p_wild:
        return _lead_out_only(
            resolver, intent, game, first, ThrowingErrorEvent, second.assist, extra=1
        )
    if r < p_wild + p_drop:
        return _lead_out_only(
            resolver, intent, game, first, FieldingErrorEvent, second.fielder, extra=0
        )
    return []


def _lead_out_only(
    resolver, intent, game, putout, error_cls, fielder, extra: int
) -> list[GameEvent]:
    """
    The lead runner is forced out but the relay to first is botched.
    The batter reaches on the error, and with a wild throw (extra=1) the
    batter and every other runner take one more base.
    """
    if game.bases.runner_on(FIRST):
        lead_base = FIRST
    elif game.bases.runner_on(THIRD):
        lead_base = THIRD
    else:
        lead_base = SECOND

    events: list[GameEvent] = [
        error_cls(fielder=fielder, batter=intent.batter),
        putout,
        RunnerRemovedEvent(
            runner=game.bases.runner_on(lead_base),
            from_base=lead_base,
            reason="fielders_choice",
        ),
    ]
    for base in (THIRD, SECOND, FIRST):
        runner = game.bases.runner_on(base)
        if runner is None or base == lead_base:
            continue
        events.append(
            RunnerAdvancedEvent(
                runner=runner,
                from_base=base,
                to_base=min(base + 1 + extra, HOME),
                reason="double_play_error",
                pitcher=intent.pitcher,
            )
        )
    events.extend(
        advance_batter_to_base(
            intent.batter, intent.pitcher, FIRST + extra, "double_play_error"
        )
    )
    events.append(OutRecordedEvent(reason="fielders_choice", pitcher=intent.pitcher))
    events.append(
        PlateAppearanceEndEvent(reason="double_play_error", batter=intent.batter)
    )
    return events


def _choose_double_play(resolver, game) -> list[PutOutEvent]:
    """
    Pick a type of double play to perform, and return the proper PutOutEvent
    """
    events: list[GameEvent] = []
    fs = FielderSelector(game.rng)

    dp_type = fs.double_play_choice.choose()
    if dp_type == "6-4-3":
        events.append(
            PutOutEvent(
                game.pos("2b"),
                game.pos("ss"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("2b"),
            )
        )
    elif dp_type == "4-6-3":
        events.append(
            PutOutEvent(
                game.pos("ss"),
                game.pos("2b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("ss"),
            )
        )
    elif dp_type == "5-4-3":
        events.append(
            PutOutEvent(
                game.pos("2b"),
                game.pos("3b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("2b"),
            )
        )
    elif dp_type == "6-3":
        events.append(PutOutEvent(game.pos("ss")))
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("ss"),
            )
        )
    elif dp_type == "4-3":
        events.append(PutOutEvent(game.pos("2b")))
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("2b"),
            )
        )
    elif dp_type == "3-6-3":
        events.append(
            PutOutEvent(
                game.pos("ss"),
                game.pos("1b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("ss"),
            )
        )
    elif dp_type == "1-6-3":
        events.append(PutOutEvent(game.pos("ss"), game.pos("p")))
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("ss"),
            )
        )
    elif dp_type == "3-6":
        events.append(PutOutEvent(game.pos("1b")))
        events.append(
            PutOutEvent(
                game.pos("ss"),
                game.pos("1b"),
            )
        )
    elif dp_type == "3-6-1":
        events.append(
            PutOutEvent(
                game.pos("ss"),
                game.pos("1b"),
            )
        )
        events.append(PutOutEvent(game.pos("p"), game.pos("ss")))
    else:  # back to 6-4-3
        events.append(
            PutOutEvent(
                game.pos("2b"),
                game.pos("ss"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("2b"),
            )
        )
    return events


def _3to1_double_play(resolver, game) -> list[PutOutEvent]:
    """
    Pick a type of double play to perform, and return the proper PutOutEvent.
    In this case we are putting out the batter and a runner on third.
    """
    events: list[GameEvent] = []
    fs = FielderSelector(game.rng)

    dp_type = fs._3to1_dp_choice.choose()
    if dp_type == "5-2-3":
        events.append(
            PutOutEvent(
                game.pos("c"),
                game.pos("3b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("c"),
            )
        )
    elif dp_type == "6-2-3":
        events.append(
            PutOutEvent(
                game.pos("c"),
                game.pos("ss"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("c"),
            )
        )
    elif dp_type == "4-2-3":
        events.append(
            PutOutEvent(
                game.pos("c"),
                game.pos("2b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("c"),
            )
        )
    elif dp_type == "1-2-3":
        events.append(
            PutOutEvent(
                game.pos("c"),
                game.pos("p"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("c"),
            )
        )
    elif dp_type == "3-2-3":
        events.append(
            PutOutEvent(
                game.pos("c"),
                game.pos("1b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("c"),
            )
        )
    elif dp_type == "5-5":
        events.append(
            PutOutEvent(
                game.pos("3b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("3b"),
            )
        )
    elif dp_type == "6-5":
        events.append(
            PutOutEvent(
                game.pos("ss"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("3b"),
                game.pos("ss"),
            )
        )
    else:  # "4-5"
        events.append(
            PutOutEvent(
                game.pos("2b"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("3b"),
                game.pos("2b"),
            )
        )

    return events


def _2to1_double_play(resolver, game) -> list[PutOutEvent]:
    """
    Pick a type of double play to perform, and return the proper PutOutEvent.
    In this case we are putting out the batter and a runner on second.
    """
    events: list[GameEvent] = []
    fs = FielderSelector(game.rng)

    dp_type = fs._2to1_dp_choice.choose()

    if dp_type == "6-3":
        events.append(PutOutEvent(game.pos("ss")))
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("ss"),
            )
        )
    elif dp_type == "6-5-3":
        events.append(
            PutOutEvent(
                game.pos("3b"),
                game.pos("ss"),
            )
        )
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("3b"),
            )
        )
    elif dp_type == "5-3":
        events.append(PutOutEvent(game.pos("3b")))
        events.append(
            PutOutEvent(
                game.pos("1b"),
                game.pos("3b"),
            )
        )
    elif dp_type == "4-6":
        events.append(PutOutEvent(game.pos("2b")))
        events.append(
            PutOutEvent(
                game.pos("ss"),
                game.pos("2b"),
            )
        )
    return events
