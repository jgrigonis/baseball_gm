# src/game/resolvers/catcher_pickoff.py
"""
Catcher pickoffs ("back picks"): after a pitch the batter takes or swings
through, with nobody stealing, the catcher fires behind a runner who
strayed too far. A strong arm and a careless runner (low base running) make
it work; the throw can also sail, or the man at the bag can drop it.
"""

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.out import OutRecordedEvent, PutOutEvent
from src.game.events.pick_off import (
    CatcherPickoffErrorEvent,
    CatcherPickoffSuccessEvent,
)
from src.game.events.runners import RunnerRemovedEvent
from src.game.probabilities import (
    CATCHER_PICKOFF_ATTEMPT_PROB,
    CATCHER_PICKOFF_DROP_FACTOR,
    CATCHER_PICKOFF_SUCCESS_PROB,
    CATCHER_PICKOFF_THROW_FACTOR,
)
from src.game.resolvers.base_running import advance_all_runners
from src.game.resolvers.errors import fielding_error_chance, throwing_error_chance
from src.game.resolvers.pick_off import bag_fielder

# Where a catcher throws behind a runner: mostly first, where the runner's
# secondary lead is longest; third now and then; second rarely.
TARGET_WEIGHTS = {FIRST: 70, THIRD: 20, SECOND: 10}
# A typical catcher's arm; better arms pick off more.
TYPICAL_CATCHER_ARM = 55


def _careless(runner) -> float:
    """How much more a runner gets caught than a typical one: 50 over his
    base running, floored at 30 like the pitcher's pickoff."""
    return 50 / max(30, runner.skills["base_running"])


def catcher_pickoff_target(resolver, game) -> int | None:
    occupied = [b for b in (FIRST, SECOND, THIRD) if game.bases.runner_on(b)]
    if not occupied:
        return None
    total = sum(TARGET_WEIGHTS[b] for b in occupied)
    r = resolver.rng.random() * total
    for b in occupied:
        r -= TARGET_WEIGHTS[b]
        if r < 0:
            return b
    return occupied[-1]


def catcher_pickoff_success_prob(catcher, runner) -> float:
    arm = max(30, catcher.skills["arm"])
    return CATCHER_PICKOFF_SUCCESS_PROB * arm / TYPICAL_CATCHER_ARM * _careless(runner)


def resolve_catcher_pickoff(resolver, intent, game) -> list[GameEvent]:
    """Maybe a back pick after this pitch. Empty when none is tried, or
    when the runner gets back safely."""
    base = catcher_pickoff_target(resolver, game)
    if base is None:
        return []
    runner = game.bases.runner_on(base)
    # Catchers look for the runner who wanders: careless ones draw more throws.
    attempt = CATCHER_PICKOFF_ATTEMPT_PROB * _careless(runner) ** 0.5
    if resolver.rng.random() >= attempt:
        return []

    catcher = game.pos("c")
    cover = bag_fielder(resolver, game, base)
    p_out = catcher_pickoff_success_prob(catcher, runner)
    p_throw = throwing_error_chance(catcher, CATCHER_PICKOFF_THROW_FACTOR)
    p_drop = fielding_error_chance(cover, CATCHER_PICKOFF_DROP_FACTOR)

    r = resolver.rng.random()
    if r < p_out:
        resolver.logger.debug(f"Catcher picks off runner at base {base}")
        return [
            CatcherPickoffSuccessEvent(base=base, runner=runner, catcher=catcher),
            PutOutEvent(fielder=cover, assist=catcher),
            OutRecordedEvent(reason="pickoff", pitcher=intent.pitcher),
            RunnerRemovedEvent(runner=runner, from_base=base, reason="pickoff"),
        ]
    if r < p_out + p_throw + p_drop:
        dropped = r >= p_out + p_throw
        events: list[GameEvent] = [
            CatcherPickoffErrorEvent(
                base=base,
                runner=runner,
                catcher=catcher,
                fielder=cover if dropped else catcher,
            )
        ]
        events.extend(
            advance_all_runners(
                game, (THIRD, SECOND, FIRST), advancement=1, reason="pickoff_error"
            )
        )
        return events
    resolver.logger.debug(f"Catcher throws behind the runner at {base}, safe")
    return []
