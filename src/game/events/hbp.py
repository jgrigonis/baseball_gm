# src/game/events/hbp.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class HitByPitchEvent(GameEvent):
    batter_id: str # TODO do we even need this?

    def apply(self, game):
        game.current_batter.player.game_stats.batting.hit_batter()
        game.current_pitcher.game_stats.pitching.hit_batter()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} was hit by pitch."
