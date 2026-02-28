# src/game/resolvers/concurrent_events.py
from typing import List

from src.game.event import GameEvent
from src.game.intents.pitch import PitchIntent
from src.game.resolvers.steal import resolve_double_steal, resolve_steal_attempt
from src.game.strategy import GameStrategy


def resolve_concurrent_events(resolver, intent: PitchIntent, game) -> List[GameEvent]:
    """
    Resolve events that happen concurrently with the pitch.

    NOTE: Steals currently do NOT happen on walks, as runners are
    already being force-advanced. This is slightly broken, as a steal
    could happen by an unforced runner. We just don't currently allow it.

    NOTE: Steals should NOT happen if runners are already being advanced
    by a wild pitch or passed ball. We should adjust so that runner
    advancement isn't 100% but steal makes it even more likely

    NOTE: Steals won't happen on a ball_in_play, as they are handled
    in resolve_ball_in_play

    """
    events = []

    if game.bases.is_empty:
        return events
    double_steal_bases = None
    from_base = None

    # Check for hit and run double steal scenarios
    if intent.pre_pitch_situation.hit_and_run:
        if game.bases.two_men_on:
            resolver.logger.debug("Hit and run double steal")
            double_steal_bases = GameStrategy.get_double_steal_candidates(game)
    else:
        double_steal_bases = intent.pre_pitch_situation.double_steal_attempt

    if double_steal_bases:
        return resolve_double_steal(resolver, double_steal_bases, intent, game)
    if intent.pre_pitch_situation.hit_and_run:
        resolver.logger.debug("Hit and run steal")
        from_base = game.bases.only_occupied_base()
    else:
        from_base = intent.pre_pitch_situation.steal_attempt
    if from_base:
        return resolve_steal_attempt(resolver, from_base, intent, game)

    return events
