# src/game/events/triple_play.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class TriplePlayEvent(GameEvent):
    """
    Adds a triple play stat for the batter and an atbat, and a triple play
    for every fielder who had a putout or assist on the play.
    """

    batter: PlayerInGame
    fielders: tuple[PlayerInGame, ...] = ()

    def apply(self, game):
        self.batter.game_stats.batting.ground_triple_play()
        self.batter.game_stats.batting.at_bat()
        for fielder in self.fielders:
            fielder.game_stats.fielding.triple_play()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit into a triple play!"
