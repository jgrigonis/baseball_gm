# src/game/resolvers/double_play.py
from typing import List

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.double_play import DoublePlayEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent


def resolve_double_play(resolver, intent, game) -> List[GameEvent]:
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

    events.append(DoublePlayEvent(batter=intent.batter, pitcher=intent.pitcher))
    if game.bases.runner_on(FIRST):
        # pick double play type
        events.extend(_choose_double_play(resolver, game))
        events.append(
            RunnerRemovedEvent(
                runner=game.bases.runner_on(FIRST),
                from_base=FIRST,
                reason="double_play",
            )
        )
        events.extend(
            resolver._advance_all_runners(
                game,
                (THIRD, SECOND),
                advancement=1,
                reason="double_play",
            )
        )

    # No runner was on first, but we still need a double play
    # try third next.
    elif game.bases.runner_on(THIRD):
        events.extend(_3to1_double_play(resolver, game))
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
        events.extend(_2to1_double_play(resolver, game))
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


def _choose_double_play(resolver, game) -> list[PutOutEvent]:
    """
    Pick a type of double play to perform, and return the proper PutOutEvent
    """
    events: list[GameEvent] = []
    dp_type = resolver.double_play_choice.choose()
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
    dp_type = resolver._3to1_dp_choice.choose()
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
    dp_type = resolver._2to1_dp_choice.choose()

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
