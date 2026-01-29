# src/game/intents/pitch.py

from dataclasses import dataclass
from typing import Optional

from src.game.intent import GameIntent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
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
    pre_pitch_situation: Optional[PrePitchSituation] = None
    # Optional advisory info (AI / UI)
    # pitch_type: Optional[str] = None
    # target: Optional[str] = None

    def to_dict(self):
        """Serialize for storage/replay."""
        return {
            "type": "PitchIntent",
            "pitcher_id": self.pitcher.id,
            "batter_id": self.batter.id,
            "situation": self._serialize_situation(),
        }

    def _serialize_situation(self):
        """Helper to serialize pre-pitch situation."""
        if not self.pre_pitch_situation:
            return None

        sit = self.pre_pitch_situation
        return {
            "steal_attempt": sit.steal_attempt,
            "double_steal_attempt": sit.double_steal_attempt,
            "bunt_attempt": sit.bunt_attempt,
            "hit_and_run": sit.hit_and_run,
            "pitch_out": sit.pitch_out,
            "intentional_walk": sit.intentional_walk,
            "pickoff_attempt": sit.pickoff_attempt,
        }

    @classmethod
    def from_dict(cls, data, game):
        """Deserialize from storage."""
        # Get situation data
        sit_data = data.get("situation")
        situation = None
        if sit_data:
            situation = PrePitchSituation(
                steal_attempt=sit_data.get("steal_attempt"),
                double_steal_attempt=sit_data.get("double_steal_attempt"),
                bunt_attempt=sit_data.get("bunt_attempt", False),
                hit_and_run=sit_data.get("hit_and_run", False),
                pitch_out=sit_data.get("pitch_out", False),
                intentional_walk=sit_data.get("intentional_walk", False),
                pickoff_attempt=sit_data.get("pickoff_attempt"),
            )

        return cls(
            pitcher=game.current_pitcher,
            batter=game.get_player(data["batter_id"]),
            pre_pitch_situation=situation,
        )
