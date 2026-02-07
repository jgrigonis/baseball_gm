# src/game/resolvers/triple_play.py

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.out import PutOutEvent, OutRecordedEvent
from src.game.events.runners import RunnerRemovedEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.resolvers.probabilities import (
    TRIPLE_PLAY_FIRST_SECOND_THRESHOLD,
    TRIPLE_PLAY_FIRST_THIRD_THRESHOLD,
)


def resolve_triple_play(resolver, intent, game):
    """
    Resolve a triple play:
    - If bases are loaded, we pick 2 runners randomly to put out
    - Otherwise, both runners are put out from whatever base they are on
    - There must be three outs.
    - Plate appearance ends
    """
    # Validation
    if game.inning.outs > 0:
        raise RuntimeError("Triple play cannot occur with outs already in the inning.")
    if len(game.bases.occupied_map()) < 2:
        raise RuntimeError(
            "Triple play cannot occur without at least 2 runners on base."
        )

    events: list[GameEvent] = []
    events.append(TriplePlayEvent(batter=intent.batter))

    if game.bases.is_loaded:
        r = resolver.rng.random()
        if r < TRIPLE_PLAY_FIRST_SECOND_THRESHOLD:
            # hard coded around the horn
            events.extend(
                [
                    PutOutEvent(game.pos("3b")),
                    PutOutEvent(game.pos("2b"), game.pos("3b")),
                    PutOutEvent(game.pos("1b"), game.pos("2b")),
                    RunnerRemovedEvent(
                        game.bases.runner_on(FIRST), FIRST, "triple_play"
                    ),
                    RunnerRemovedEvent(
                        game.bases.runner_on(SECOND), SECOND, "triple_play"
                    ),
                ]
            )
        elif r < TRIPLE_PLAY_FIRST_THIRD_THRESHOLD:
            # line out to third baseman, tag third, throw behind runner leaving first
            events.extend(
                [
                    PutOutEvent(game.pos("3b")),
                    PutOutEvent(game.pos("3b")),
                    PutOutEvent(game.pos("1b"), game.pos("3b")),
                    RunnerRemovedEvent(
                        game.bases.runner_on(FIRST), FIRST, "triple_play"
                    ),
                    RunnerRemovedEvent(
                        game.bases.runner_on(THIRD), THIRD, "triple_play"
                    ),
                ]
            )
        else:
            # around the horn
            events.extend(
                [
                    PutOutEvent(game.pos("3b")),
                    PutOutEvent(game.pos("2b"), game.pos("3b")),
                    PutOutEvent(game.pos("1b"), game.pos("2b")),
                    RunnerRemovedEvent(
                        game.bases.runner_on(THIRD), THIRD, "triple_play"
                    ),
                    RunnerRemovedEvent(
                        game.bases.runner_on(SECOND), SECOND, "triple_play"
                    ),
                ]
            )
    else:
        # bases not loaded, must be two runners on, both are out
        events.extend(
            [
                PutOutEvent(game.pos("3b")),
                PutOutEvent(game.pos("2b"), game.pos("3b")),
                PutOutEvent(game.pos("1b"), game.pos("2b")),
            ]
        )

        for base in (FIRST, SECOND, THIRD):
            if game.bases.runner_on(base):
                events.append(
                    RunnerRemovedEvent(game.bases.runner_on(base), base, "triple_play")
                )

    events.extend(
        [
            OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher),
            OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher),
            OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher),
            PlateAppearanceEndEvent(reason="triple_play", batter=intent.batter),
        ]
    )

    return events
