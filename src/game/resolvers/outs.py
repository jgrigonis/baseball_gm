# src/game/resolvers/outs.py

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.error import FieldingErrorEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
    FlyOutEvent,
    GroundOutEvent,
)
from src.game.events.runners import RunnerAdvancedEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent


def resolve_fly_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a fly out"""
    events: list[GameEvent] = []
    lf_arm = game.pos("lf").skills["arm"]
    cf_arm = game.pos("cf").skills["arm"]
    rf_arm = game.pos("rf").skills["arm"]
    arm = resolver.rng.choice([lf_arm, cf_arm, rf_arm])

    tag_from_second, tag_from_first = resolver.adjust_tagup_probs(game.bases, arm)
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


def resolve_ground_out(resolver, intent, game) -> list[GameEvent]:
    """Resolve a ground out"""
    events: list[GameEvent] = []

    # Determine which infielder fields the ball
    fielder = resolver._select_infielder(game)
    fielding_skill = fielder.skills["infield"]

    # Check if fielder makes an error
    error_prob = resolver._calculate_error_probability(fielding_skill)

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
