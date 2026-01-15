# src/game/events.py
class GameEvent:
    def apply(self, game):
        raise NotImplementedError
