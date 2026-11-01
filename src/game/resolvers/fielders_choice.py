# src/game/resolvers/fielders_choice.py

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.resolvers.base_running import advance_all_runners, advance_batter_to_base
from src.game.resolvers.errors import everyone_safe_on_error, force_play_error
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.probabilities import FC_FIELD_FACTOR, FC_THROW_FACTOR, FC_DROP_FACTOR


def resolve_fielders_choice(resolver, intent, game) -> list[GameEvent]:
    """
    Fielder's choice can result in no outs.

    The official scorers must deem that had the fielder chosen to throw to
    1B, that it would have been a routine play.

    If they try to get the lead runner instead and fail, then it would be
    a fielder's choice.

    A run scores on a fielder's choice when the defense prioritizes getting
    another runner, and that play allows the run to cross the plate before
    the defense gets an out on the batter or another forced runner.

    The default is one out, but there doesn't need to be an out necessarily

    algorithm:
    - pick one runner to put out, move all other runners forward one base.
    - If there is a runner on third, pick that one
    - Else pick the runner on first
    - Else the runner on second
    - Place the batter on first
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runners=True)

    fs = FielderSelector(game.rng)

    events: list[GameEvent] = []
    events.append(FieldersChoiceEvent(batter=intent.batter, pitcher=intent.pitcher))

    if game.bases.runner_on(THIRD):
        # throw out at plate
        events.append(PutOutEvent(game.pos("c"), fs.select_infielder(game)))
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(THIRD),
                from_base=THIRD,
                reason="fielders_choice",
            )
        )
        # Advance other runners
        events.extend(
            advance_all_runners(
                game,
                (SECOND, FIRST),
                advancement=1,
                reason="fielders_choice",
            )
        )

    elif game.bases.runner_on(FIRST):
        # force out at second
        if resolver.rng.random() < 0.5:
            if resolver.rng.random() < 0.7:
                events.append(
                    PutOutEvent(
                        game.pos("ss"),
                        game.pos("2b"),
                    )
                )
            else:
                events.append(
                    PutOutEvent(
                        game.pos("ss"),
                        game.pos("3b"),
                    )
                )
        else:
            if resolver.rng.random() < 0.7:
                events.append(
                    PutOutEvent(
                        game.pos("2b"),
                        game.pos("ss"),
                    )
                )
            else:
                events.append(
                    PutOutEvent(
                        game.pos("2b"),
                        game.pos("3b"),
                    )
                )
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(FIRST),
                from_base=FIRST,
                reason="fielders_choice",
            )
        )
        # Advance runner on second if present
        runner = game.bases.runner_on(SECOND)
        if runner:
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=SECOND,
                    to_base=THIRD,
                    reason="fielders_choice",
                    pitcher=intent.pitcher,
                )
            )

    else:
        # runner on second, just have the shortstop tag him out
        events.append(PutOutEvent(game.pos("ss")))
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(SECOND),
                from_base=SECOND,
                reason="fielders_choice",
            )
        )

    # The force/tag play itself can be botched: then nobody is out, the
    # batter reaches on the error and every runner moves up a base.
    putout = next(e for e in events if isinstance(e, PutOutEvent))
    error = force_play_error(
        resolver, putout, FC_FIELD_FACTOR, FC_THROW_FACTOR, FC_DROP_FACTOR
    )
    if error:
        return everyone_safe_on_error(
            resolver, intent, game, error, reason="fielders_choice_error"
        )

    # Batter to first
    events.extend(
        advance_batter_to_base(intent.batter, intent.pitcher, FIRST, "fielders_choice")
    )
    events.append(OutRecordedEvent(reason="fielders_choice", pitcher=intent.pitcher))
    events.append(
        PlateAppearanceEndEvent(reason="fielders_choice", batter=intent.batter)
    )

    return events
