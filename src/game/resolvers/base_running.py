# src/game/resolvers/base_running.py
from src.game.bases import HOME
from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent


def advance_all_runners(
    game, bases: tuple, advancement: int, reason: str, rbi_batter=None
) -> list[GameEvent]:
    """Advance runners on specified bases by advancement amount (capped at HOME)"""
    events = []
    for base in bases:
        runner = game.bases.runner_on(base)
        if not runner:
            continue

        events.append(
            RunnerAdvancedEvent(
                runner=runner,
                from_base=base,
                to_base=min(base + advancement, HOME),
                reason=reason,
                rbi_batter=rbi_batter,
                pitcher=game.pos("p"),
            )
        )
    return events


def advance_batter_to_base(
    batter: str, pitcher: str, to_base: int, reason: str
) -> RunnerAdvancedEvent:
    """Create event for batter advancing to a base"""
    return RunnerAdvancedEvent(
        runner=batter,
        from_base=None,
        to_base=to_base,
        reason=reason,
        pitcher=pitcher,
    )
