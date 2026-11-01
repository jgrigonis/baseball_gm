# src/game/resolvers/errors.py
"""
Shared error-chance helpers.

Every play that involves a fielder handling the ball or making a throw can
go wrong. These helpers turn a fielder's ratings into the chance of a
fielding error (booted / dropped ball) or a throwing error (bad throw), so
each resolver scales them by how hard its particular play is.

For a typical starter (position rating ~78, arm ~65):
    fielding_error_prob ~ 2.7%   (a hard ground ball to an infielder)
    throwing_error_prob ~ 2.1%   (a full-length throw across the diamond)

Easier plays (a short feed to second, catching a routine fly) multiply
these down with the *_FACTOR constants in src.game.probabilities.
"""

from src.game.bases import FIRST, SECOND, THIRD
from src.game.events.error import FieldingErrorEvent, ThrowingErrorEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.probabilities import BASE_ERROR_RATE
from src.game.resolvers.base_running import advance_all_runners, advance_batter_to_base


def fielder_rating(fielder) -> int:
    """The fielder's rating at the position he is playing (50 if unknown)."""
    ratings = getattr(fielder, "ratings", None)
    position = getattr(fielder, "current_position", None)
    value = ratings.get(position, 50) if isinstance(ratings, dict) else 50
    return value if isinstance(value, (int, float)) else 50


def fielder_arm(fielder) -> int:
    skills = getattr(fielder, "skills", None)
    try:
        value = skills["arm"]
    except (KeyError, TypeError):
        return 50
    return value if isinstance(value, (int, float)) else 50


def fielding_error_prob(fielding_skill: int) -> float:
    """Chance of booting a ground ball, scaled by position rating."""
    return BASE_ERROR_RATE * (100 - fielding_skill) / 50


def throwing_error_prob(fielding_skill: int, arm_skill: int) -> float:
    """Chance of a bad throw, scaled by position rating and arm."""
    return BASE_ERROR_RATE * 0.6 * (200 - fielding_skill - arm_skill) / 100


def fielding_error_chance(fielder, factor: float = 1.0) -> float:
    """fielding_error_prob for this fielder, scaled by how hard the play is."""
    return fielding_error_prob(fielder_rating(fielder)) * factor


def throwing_error_chance(fielder, factor: float = 1.0) -> float:
    """throwing_error_prob for this fielder, scaled by how hard the throw is."""
    return throwing_error_prob(fielder_rating(fielder), fielder_arm(fielder)) * factor


def force_play_error(resolver, putout, field_factor, throw_factor, drop_factor):
    """
    Walk one fielded-and-thrown force play (a PutOutEvent) and see whether
    it breaks down: the first fielder boots the ball, his throw is bad, or
    the man covering the bag drops it.

    Returns (error_event_class, fielder) or None when the play is made.
    """
    fielded_by = putout.assist or putout.fielder
    p_field = fielding_error_chance(fielded_by, field_factor)
    p_throw = p_drop = 0.0
    if putout.assist is not None and putout.assist is not putout.fielder:
        p_throw = throwing_error_chance(putout.assist, throw_factor)
        p_drop = fielding_error_chance(putout.fielder, drop_factor)

    r = resolver.rng.random()
    if r < p_field:
        return FieldingErrorEvent, fielded_by
    if r < p_field + p_throw:
        return ThrowingErrorEvent, putout.assist
    if r < p_field + p_throw + p_drop:
        return FieldingErrorEvent, putout.fielder
    return None


def handle_fielding_error_advancement(resolver, intent, game):
    """Everyone is safe: runners move up one base, batter to first."""
    events = advance_all_runners(
        game,
        (THIRD, SECOND, FIRST),
        advancement=1,
        reason="fielding_error",
        rbi_batter=intent.batter,
    )
    events.extend(
        advance_batter_to_base(intent.batter, intent.pitcher, FIRST, "fielding_error")
    )
    return events


def everyone_safe_on_error(resolver, intent, game, error, reason):
    """
    The play broke down before any out was made: the batter reaches on the
    error and every runner moves up a base. Ends the plate appearance.
    """
    event_cls, fielder = error
    events = [event_cls(fielder=fielder, batter=intent.batter)]
    events.extend(handle_fielding_error_advancement(resolver, intent, game))
    events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))
    return events
