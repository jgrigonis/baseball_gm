# src/game/rules/play_outcome.py

from src.game.event_outcome import EventOutcome


def build_play_outcome(raw: str) -> EventOutcome:
    match raw:
        case "single":
            return EventOutcome(type="hit", bases=1)
        case "double":
            return EventOutcome(type="hit", bases=2)
        case "home_run":
            return EventOutcome(type="home_run", bases=4)
        case "double_play":
            return EventOutcome(type="double_play", is_out=True)
        case _:
            raise ValueError(f"Unknown play outcome: {raw}")
