# src/game/events/pitch.py
from dataclasses import dataclass

from src.game.count import CountSnapshot
from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class PitchThrownEvent(GameEvent):
    """
    A pitch has been thrown.
    This is observational only.
    It does add to the pitch count.
    """

    pitcher: PlayerInGame
    batter: PlayerInGame
    count: CountSnapshot
    pitch_type: str | None = None  # fastball, curve, etc. (optional for now)

    def apply(self, game):
        game.logger.trace("PitchThrownEvent applied")
        self.pitcher.game_stats.pitching.pitch()
        # Only track fatigue if this is actually a pitcher
        if self.pitcher.pitcher_fatigue is not None:
            self.pitcher.pitcher_fatigue.add_pitch(pitch_type=self.pitch_type)

    def should_log(self, game) -> bool:
        """We don't need to log every pitch."""
        return False
