# src/game/events.py
class GameEvent:
    def apply(self, game):
        raise NotImplementedError

    def label(self) -> str:
        return self.__class__.__name__
