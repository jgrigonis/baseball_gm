# In src/game/events/error.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame

@dataclass
class FieldingErrorEvent(GameEvent):
    fielder: PlayerInGame
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} got on base via an error."


@dataclass
class ThrowingErrorEvent(GameEvent):
    fielder: PlayerInGame
    runner: PlayerInGame
    from_base: int
    to_base: int

