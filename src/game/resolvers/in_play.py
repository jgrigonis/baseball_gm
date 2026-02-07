# src/game/resolvers/in_play.py
from src.game.event import GameEvent
from src.game.resolvers.double_play import resolve_double_play
from src.game.resolvers.fielders_choice import resolve_fielders_choice
from src.game.resolvers.hits import resolve_single, resolve_double, resolve_triple
from src.game.resolvers.outs import resolve_fly_out, resolve_ground_out
from src.game.resolvers.sacrifices import resolve_sac_bunt, resolve_sac_fly
from src.game.resolvers.triple_play import resolve_triple_play


def resolve_ball_in_play(resolver, intent, game, foul=False) -> list[GameEvent]:
    """
    Resolve a ball put into play.

    Must:
    - use rng
    - not mutate game
    - return concrete events
    """
    # Reset to base weights
    resolver.in_play_outcome.reset()

    # Apply all modifiers
    resolver._apply_in_play_modifiers(game)

    # Make the choice
    outcome = resolver.in_play_outcome.choose()

    outcome_handlers = {
        "fly_out": resolve_fly_out,
        "ground_out": resolve_ground_out,
        "single": resolve_single,
        "double": resolve_double,
        "triple": resolve_triple,
        "double_play": resolve_double_play,
        "fielders_choice": resolve_fielders_choice,
        "sac_fly": resolve_sac_fly,
        "sac_bunt": resolve_sac_bunt,
        "triple_play": resolve_triple_play,
    }
    resolver.logger.trace(f"in_play_outcome = {outcome}")
    if outcome in outcome_handlers:
        return outcome_handlers[outcome](resolver, intent, game)

    raise RuntimeError(f"Unknown in-play outcome: {outcome}")
