# src/game/resolvers/pitch.py

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.error import ErrorChargedEvent
from src.game.events.strike import DroppedThirdStrikeEvent
from src.game.probabilities import (
    DROPPED_THIRD_STRIKE_LOOKING_MOD,
    DROPPED_THIRD_STRIKE_PROB,
    DROPPED_THIRD_STRIKE_REACH_PROB,
    DROPPED_THIRD_STRIKE_TAG_PROB,
    DROPPED_THIRD_STRIKE_THROW_FACTOR,
    DROPPED_THIRD_STRIKE_WP_SHARE,
)
from src.game.resolvers.base_running import advance_all_runners, advance_batter_to_base
from src.game.resolvers.errors import fielder_rating, throwing_error_chance
from src.game.events.balk import BalkEvent
from src.game.events.ball import BallEvent, IllegalPitch
from src.game.events.noop import NoOpEvent
from src.game.events.out import PutOutEvent, OutRecordedEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.strike import StrikeEvent
from src.game.events.strikeout import StrikeOutEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.intents.pitch import PitchIntent
from src.game.resolvers.fouls import resolve_foul
from src.game.resolvers.hits import resolve_home_run
from src.game.resolvers.in_play import resolve_ball_in_play
from src.game.resolvers.walk import resolve_walk


def resolve_ball(resolver, intent, game) -> list[GameEvent]:
    """Handle a ball being called"""
    events = [BallEvent()]
    if game.count.balls + 1 >= 4:
        events.extend(resolve_walk(resolver, intent, game))
    return events


def resolve_strike(
    resolver, outcome: str, intent: PitchIntent, game
) -> list[GameEvent]:
    """Handle different types of strikes"""
    # A bare "strike" (test overrides) counts as called.
    swinging = outcome == "swinging_strike"
    events = [StrikeEvent(swinging=swinging)]

    # Check for strikeout
    if game.count.strikes + 1 >= 3:
        resolver.logger.debug("strike out ending pa")
        strikeout = StrikeOutEvent(
            batter=intent.batter, pitcher=intent.pitcher, swinging=swinging
        )
        if _strike_three_dropped(resolver, game, swinging):
            events.extend(_dropped_third_strike(resolver, intent, game, strikeout))
            return events
        events.extend(
            [
                strikeout,
                PutOutEvent(game.pos("c")),
                OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher),
                PlateAppearanceEndEvent(reason="strikeout", batter=intent.batter),
            ]
        )

    return events


def _strike_three_dropped(resolver, game, swinging: bool) -> bool:
    """The batter may run on strike three when first base is open or there
    are two outs; this is the chance the catcher didn't hold it. A better
    catcher (his rating behind the plate) drops fewer."""
    if game.bases.runner_on(FIRST) is not None and game.inning.outs < 2:
        return False
    catcher = game.pos("c")
    p = DROPPED_THIRD_STRIKE_PROB * (100 - fielder_rating(catcher)) / 22
    if not swinging:
        p *= DROPPED_THIRD_STRIKE_LOOKING_MOD
    return resolver.rng.random() < p


def _dropped_third_strike(resolver, intent, game, strikeout) -> list[GameEvent]:
    """Strike three got by the catcher. The pitcher still gets his strikeout.
    Most of the time the catcher picks it up and tags the batter or throws
    him out at first (a bad throw puts him on); now and then it rolls far
    enough that he makes first, a wild pitch or a passed ball."""
    catcher = game.pos("c")
    events: list[GameEvent] = [DroppedThirdStrikeEvent(batter=intent.batter), strikeout]
    r = resolver.rng.random()
    if r < DROPPED_THIRD_STRIKE_REACH_PROB:
        if resolver.rng.random() < DROPPED_THIRD_STRIKE_WP_SHARE:
            events.append(WildPitchEvent(pitcher=intent.pitcher))
            reason = "strikeout_wild_pitch"
        else:
            events.append(PassedBallEvent(catcher=catcher, pitcher=intent.pitcher))
            reason = "strikeout_passed_ball"
        events.extend(
            advance_batter_to_base(intent.batter, intent.pitcher, FIRST, reason)
        )
        events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))
        return events

    if resolver.rng.random() < DROPPED_THIRD_STRIKE_TAG_PROB:
        events.append(PutOutEvent(catcher))
    else:
        if resolver.rng.random() < throwing_error_chance(
            catcher, DROPPED_THIRD_STRIKE_THROW_FACTOR
        ):
            # Into right field: everyone moves up, the batter takes first.
            events.append(ErrorChargedEvent(fielder=catcher))
            events.extend(
                advance_all_runners(game, (THIRD, SECOND, FIRST), 1, "strikeout_error")
            )
            events.extend(
                advance_batter_to_base(
                    intent.batter, intent.pitcher, FIRST, "strikeout_error"
                )
            )
            events.append(
                PlateAppearanceEndEvent(reason="strikeout_error", batter=intent.batter)
            )
            return events
        events.append(PutOutEvent(fielder=game.pos("1b"), assist=catcher))
    events.append(OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher))
    events.append(
        PlateAppearanceEndEvent(reason="strikeout_dropped", batter=intent.batter)
    )
    return events


def resolve_illegal_pitch(resolver, intent, game) -> list[GameEvent]:
    """Handle an illegal pitch"""
    events = [IllegalPitch(pitcher=intent.pitcher), BallEvent()]
    if game.count.balls + 1 >= 4:
        events.extend(resolve_walk(resolver, intent, game))
    return events


def resolve_balk(resolver, game) -> list[GameEvent]:
    """Handle a balk"""
    if game.bases.is_empty:
        resolver.logger.trace("Balk called with no runners on.")
        return []
    return [BalkEvent(pitcher=game.pos("p"))]


def resolve_wild_pitch(resolver, intent, game) -> list[GameEvent]:
    """Handle a wild pitch"""
    events = []
    # Always add the ball
    events.append(BallEvent())

    # Add wild pitch event if runners on (BEFORE walk logic)
    if not game.bases.is_empty:
        events.append(WildPitchEvent(pitcher=game.pos("p")))
    else:
        resolver.logger.trace("Wild Pitch occurred with no runners on.")

    # Check for walk
    if game.count.balls + 1 >= 4:
        events.extend(resolve_walk(resolver, intent, game, skip_force_advance=True))
    return events


def resolve_passed_ball(resolver, intent, game) -> list[GameEvent]:
    """Handle a passed ball"""
    events = []
    # Always add the ball
    events.append(BallEvent())

    # Add passed ball event if runners on (BEFORE walk logic)
    if not game.bases.is_empty:
        events.append(
            PassedBallEvent(
                catcher=game.pos("c"),
                pitcher=game.pos("p"),
            )
        )
    else:
        resolver.logger.trace("Passed Ball occurred with no runners on.")

    # Check for walk
    if game.count.balls + 1 >= 4:
        events.extend(resolve_walk(resolver, intent, game, skip_force_advance=True))
    return events


PITCH_OUTCOME_HANDLERS = {
    "in_play": resolve_ball_in_play,
    "ball": resolve_ball,
    "strike": resolve_strike,
    "called_strike": resolve_strike,
    "swinging_strike": resolve_strike,
    "foul": resolve_foul,
    "hit_by_pitch": lambda r, i, g: resolve_walk(r, i, g, hbp=True),
    "catcher_interference": lambda r, i, g: resolve_walk(
        r, i, g, catcher_interference=True
    ),
    "illegal_pitch": resolve_illegal_pitch,
    "balk": resolve_balk,
    "wild_pitch": resolve_wild_pitch,
    "passed_ball": resolve_passed_ball,
    "home_run": resolve_home_run,
}


def resolve_pitch(resolver, intent: PitchIntent, game) -> list[GameEvent]:
    events: list[GameEvent] = []

    # ------------------------------------------------------------
    # 1. Pitch is always thrown
    # ------------------------------------------------------------
    events.append(
        PitchThrownEvent(
            pitcher=intent.pitcher,
            batter=intent.batter,
            count=game.count.snapshot(),
            # pitch_type=intent.pitch_type,
        )
    )

    # ------------------------------------------------------------
    # 2. Determine outcome (pure decision)
    # ------------------------------------------------------------
    outcome = determine_pitch_outcome(resolver, intent, game)
    resolver.logger.trace(outcome)

    # Sanity check
    assert outcome in (
        "ball",
        "strike",
        "called_strike",
        "swinging_strike",
        "foul",
        "hit_by_pitch",
        "catcher_interference",
        "illegal_pitch",
        "balk",
        "wild_pitch",
        "passed_ball",
        "home_run",
        "in_play",
    )

    # ------------------------------------------------------------
    # 3. Emit outcome specific events
    # ------------------------------------------------------------
    handler = PITCH_OUTCOME_HANDLERS.get(outcome)
    if handler:
        # Special case for strike outcomes that need the outcome type
        if outcome in ("strike", "called_strike", "swinging_strike"):
            events.extend(handler(resolver, outcome, intent, game))
        # Balk doesn't need intent
        elif outcome == "balk":
            events.extend(handler(resolver, game))
        else:
            events.extend(handler(resolver, intent, game))
    else:
        events.extend([NoOpEvent()])

    resolver.logger.trace(f"events = {events}")
    return events


def determine_pitch_outcome(resolver, intent, game) -> str:
    """Delegate to resolver method (enables test override)."""
    return resolver.determine_pitch_outcome(intent, game)
