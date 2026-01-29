# src/game/intents/pitch.py
from dataclasses import dataclass
from typing import Optional

from src.game.intent import GameIntent
from src.player.player_in_game import PlayerInGame


@dataclass
class PrePitchSituation:
    """Tactical decisions made before pitch delivery"""

    # Offense
    steal_attempt: Optional[int] = None
    double_steal_attempt: Optional[list[int]] = None
    bunt_attempt: bool = False
    hit_and_run: bool = False

    # Defense
    pitch_out: bool = False
    intentional_walk: bool = False
    pickoff_attempt: Optional[int] = None  # Which base?


@dataclass(frozen=True)
class PitchIntent(GameIntent):
    pitcher: PlayerInGame
    batter: PlayerInGame
    pre_pitch_situation: PrePitchSituation = None
    # Optional advisory info (AI / UI)
    # pitch_type: Optional[str] = None
    # target: Optional[str] = None

    def to_dict(self):
        """Serialize for storage/replay."""
        return {
            "type": "PitchIntent",
            "pitcher_id": self.pitcher.id,
            "batter_id": self.batter.id,
            "pitch_type": self.pitch_type,
        }

    # TODO fix this up
    # @classmethod
    # def from_dict(cls, data, game):
    #     """Deserialize from storage."""
    #     return cls(
    #         pitcher=game.current_pitcher,
    #         batter=game.get_player(data['batter_id']),
    #         pitch_type=data.get('pitch_type'),
    #     )
