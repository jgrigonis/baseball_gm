# src/game/resolvers/fouls.py
from src.game.event import GameEvent
from src.game.events.out import (
    OutRecordedEvent,
    FoulFlyOutEvent,
    PutOutEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.strike import (
    FoulStrikeEvent,
    FouledOffThirdStrikeEvent,
    FoulTipCaughtThirdStrikeEvent,
)
from src.game.events.strikeout import StrikeOutEvent
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.probabilities import (
    FOUL_TIP_CAUGHT_PROB,
    FOULED_OFF_THIRD_STRIKE_PROB,
    FOUL_FLY_OUT_BEFORE_TWO_STRIKES_PROB,
)


def resolve_foul(resolver, intent, game) -> list[GameEvent]:
    """
    Resolve a foul ball.

    Must:
    - use rng
    - not mutate game
    - return concrete events
    """
    events: list[GameEvent] = []

    if game.count.strikes + 1 >= 3:
        r = resolver.rng.random()
        foul_tip_caught_prob = (
            FOUL_TIP_CAUGHT_PROB * game.pos("c").skills["catching"] / 50
        )
        if r < foul_tip_caught_prob:
            resolver.logger.debug("foul tip strike out ending pa")
            events.extend(
                [
                    FoulTipCaughtThirdStrikeEvent(),
                    StrikeOutEvent(batter=intent.batter, pitcher=intent.pitcher),
                    PutOutEvent(game.pos("c")),
                    OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher),
                    PlateAppearanceEndEvent(reason="strikeout", batter=intent.batter),
                ]
            )
        elif r < FOULED_OFF_THIRD_STRIKE_PROB:
            events.append(FouledOffThirdStrikeEvent())
        else:
            events.extend(resolve_fly_out_foul(resolver, intent, game))

    else:  # less than 2 strikes
        r = resolver.rng.random()
        if r < FOUL_FLY_OUT_BEFORE_TWO_STRIKES_PROB:
            events.extend(resolve_fly_out_foul(resolver, intent, game))
        else:
            events.append(FoulStrikeEvent(swinging=True))

    return events


def resolve_fly_out_foul(resolver, intent, game) -> list[GameEvent]:
    """Simply resolves a fly out foul, can happen with 2 strikes or less."""
    fs = FielderSelector(game.rng)

    return [
        FoulFlyOutEvent(batter=intent.batter),
        PutOutEvent(fs.select_foul_out_catcher(game)),
        OutRecordedEvent(reason="foul_fly_out", pitcher=intent.pitcher),
        PlateAppearanceEndEvent(reason="out", batter=intent.batter),
    ]
