# src/game/resolvers/pitch.py

from src.game.event import GameEvent
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
        events.extend(
            [
                StrikeOutEvent(
                    batter=intent.batter, pitcher=intent.pitcher, swinging=swinging
                ),
                PutOutEvent(game.pos("c")),
                OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher),
                PlateAppearanceEndEvent(reason="strikeout", batter=intent.batter),
            ]
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
