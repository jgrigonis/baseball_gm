# src/game/resolvers/walk.py

from src.game.bases import FIRST
from src.game.events.hbp import HitByPitchEvent
from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.rules.force_advancement import force_advance_chain


def resolve_walk(
    resolver,
    intent,
    game,
    hbp=False,
    intentional=False,
    catcher_interference=False,
    skip_force_advance=False,
):
    """
    Resolves a walk. Will deal with hit by pitch, and intentional walks as well.

    Also handles the catcher interference case.

    It will force forward runners as necessary to make room for the batter on first.
    """
    resolver.logger.trace("Entering _resolve_walk")
    resolver.logger.debug(game.bases)

    events = []

    if hbp:
        reason = "intentional_hit_by_pitch" if intentional else "hit_by_pitch"
        events.append(HitByPitchEvent(batter=intent.batter, pitcher=intent.pitcher))
    else:
        if intentional:
            reason = "intentional_walk"
            events.append(IBBEvent(batter=intent.batter, pitcher=intent.pitcher))
        elif catcher_interference:
            reason = "catcher_interference"
            events.append(
                CatcherInterferenceEvent(
                    batter=intent.batter,
                    pitcher=intent.pitcher,
                    catcher=game.pos("c"),
                )
            )
        else:
            reason = "walk"
            events.append(WalkEvent(pitcher=intent.pitcher, batter=intent.batter))

    # Force existing runners
    if not skip_force_advance:
        occupied = game.bases.occupied_map()

        forced = force_advance_chain(
            occupied_bases=occupied,
            start_base=1,
            rbi_batter=intent.batter,
        )
        for f in forced:
            events.append(
                RunnerAdvancedEvent(
                    runner=f.runner,
                    from_base=f.from_base,
                    to_base=f.to_base,
                    reason=f.reason,
                    rbi_batter=f.rbi_batter,
                    pitcher=intent.pitcher,
                )
            )

    # Award batter first base
    events.append(
        resolver._advance_batter_to_base(intent.batter, intent.pitcher, FIRST, reason)
    )

    resolver.logger.trace("Ending PA in _resolve_walk")
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

    return events
