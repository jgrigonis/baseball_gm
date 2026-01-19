# src/game/events.py
class GameEvent:
    def apply(self, game):
        raise NotImplementedError

    def label(self) -> str:
        return self.__class__.__name__

    def should_log(self) -> bool:
        """Whether this event should be logged at INFO level."""
        return True  # Default: log most events

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return self.label()  # Default fallback
