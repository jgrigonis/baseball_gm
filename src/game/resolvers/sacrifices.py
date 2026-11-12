# src/game/resolvers/sacrifices.py

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.out import (
    PutOutEvent,
    OutRecordedEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.events.sacrifice import SacBuntEvent, SacFlyEvent
from src.game.resolvers.base_running import advance_all_runners
from src.game.resolvers.errors import (
    everyone_safe_on_error,
    force_play_error,
    throwing_error_chance,
)
from src.game.resolvers.fielder_selector import FielderSelector
from src.game.resolvers.outs import _thrown_out_tagging, _tag_up_double_play
from src.game.events.error import OutfielderThrowingErrorEvent
from src.game.probabilities import (
    BUNT_FIELD_FACTOR,
    BUNT_THROW_FACTOR,
    BUNT_DROP_FACTOR,
    SAC_FLY_THROW_FACTOR,
)


def resolve_sac_bunt(resolver, intent, game) -> list[GameEvent]:
    """
    A sac bunt must be a bunt. There can't be 2 outs.

    - move a runner from 1st to 2nd if no other runners
    - move a runner from 2nd to third if no other runners
    - score a runner from 3rd if no other runners
    - all runners should advance if multiple.
    - put out the batter
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runners=True)

    fs = FielderSelector(game.rng)

    events: list[GameEvent] = []

    fielder = fs.select_infielder_bunt(game)
    putout = (
        PutOutEvent(game.pos("1b"))
        if fielder is game.pos("1b")
        else PutOutEvent(game.pos("1b"), fielder)
    )
    # A charging fielder throwing on the run: the bunt play can be botched,
    # and then the batter is safe too.
    error = force_play_error(
        resolver, putout, BUNT_FIELD_FACTOR, BUNT_THROW_FACTOR, BUNT_DROP_FACTOR
    )
    if error:
        return everyone_safe_on_error(
            resolver, intent, game, error, reason="sac_bunt_error"
        )

    events.append(SacBuntEvent(batter=intent.batter))
    events.append(putout)
    events.append(OutRecordedEvent(reason="sac_bunt", pitcher=intent.pitcher))

    # Advance all runners one base
    events.extend(
        advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=1,
            reason="sac_bunt",
            rbi_batter=intent.batter,
        )
    )

    events.append(PlateAppearanceEndEvent(reason="sac_bunt", batter=intent.batter))

    return events


def resolve_sac_fly(resolver, intent, game) -> list[GameEvent]:
    """
    A sac fly must result in a score. There can't be 2 outs.

    - score the runner on third
    - put out the batter
    """
    # Validation
    resolver._validate_game_state(game, max_outs=2, require_runner_on=THIRD)
    fs = FielderSelector(game.rng)

    events: list[GameEvent] = []

    outfielder = fs.select_outfielder(game)
    runner = game.bases.runner_on(THIRD)
    # A strong throw can beat him home: no run, a fly ball double play.
    if _thrown_out_tagging(resolver, outfielder, runner, HOME):
        return _tag_up_double_play(resolver, intent, game, outfielder, runner, THIRD)
    events.append(SacFlyEvent(batter=intent.batter))
    events.append(PutOutEvent(outfielder))
    events.append(OutRecordedEvent(reason="sac_fly", pitcher=intent.pitcher))

    events.append(
        RunnerAdvancedEvent(
            runner=runner,
            from_base=THIRD,
            to_base=HOME,
            reason="sac_fly",
            rbi_batter=intent.batter,
            pitcher=intent.pitcher,
        )
    )
    # Advance the runners from first and second also
    # TODO Should be a variable chance to change this.
    # based on runner speed and the arm of fs
    # A bad throw home lets the trailing runners take an extra base.
    trailing = [b for b in (SECOND, FIRST) if game.bases.runner_on(b)]
    if trailing and resolver.rng.random() < throwing_error_chance(
        outfielder, SAC_FLY_THROW_FACTOR
    ):
        events.append(
            OutfielderThrowingErrorEvent(
                fielder=outfielder, runner=game.bases.runner_on(trailing[0])
            )
        )
        events.extend(
            advance_all_runners(
                game, (SECOND, FIRST), advancement=2, reason="sac_fly_error"
            )
        )
    else:
        events.extend(
            advance_all_runners(
                game,
                (SECOND, FIRST),
                advancement=1,
                reason="ground_out",
            )
        )

    events.append(PlateAppearanceEndEvent(reason="sac_fly", batter=intent.batter))

    return events
