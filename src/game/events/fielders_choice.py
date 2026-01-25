# src/game/events/fielder_choice.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class FieldersChoiceEvent(GameEvent):
    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.out()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit into a fielder's choice."
