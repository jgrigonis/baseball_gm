# src/game/events.py
import logging


class GameEvent:
    def apply(self, game):
        raise NotImplementedError

    def label(self) -> str:
        return self.__class__.__name__

    def log_level(self) -> int:
        """Return logging level for this event."""
        return logging.INFO  # Default

    def should_log(self, game) -> bool:
        """Whether this event should be logged at INFO level."""
        return True  # Default: log most events

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return self.label()  # Default fallback
