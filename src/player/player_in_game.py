# src/player/player_in_game.py
"""
The PlayerInGame class.

PlayerRecord  ── snapshot ──▶  PlayerInGame
      ▲                              │
      └────── apply results ◀────────┘

✔ Safe to mutate
✔ Easy to reset
✔ Deterministic per game

PlayerRecord = immutable, authoritative, season-persistent
PlayerInGame = ephemeral, mutable, game-specific

✅ Valid states for PlayerInGame.ratings
State	= Representation
Unrated	= ratings attribute does not exist
Rated	= ratings is a dict
"""

from src.stats.fielding_stats import FieldingStats
import src.stats.stats as stats

from src.player.fatigue import PitcherFatigue
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.position_fatigue import PositionPlayerFatigue


class PlayerInGame(object):
    """A Baseball Player in the game."""

    def __init__(self, record: PlayerRecord):
        self.record = record  # reference, not copied
        self.id = record.id  # convenience
        # self.name = record.name
        self.first_name = record.first_name
        self.last_name = record.last_name

        # immutable traits for this game
        self.bats = record.bats
        self.throws = record.throws
        self.skills = record.skills  # read-only by convention

        # mutable, game-only state
        self.game_stats = stats.GameStats()
        self.fielding_by_position: dict[str, FieldingStats] = {}
        self._current_position: str | None = None
        self.responsible_pitcher: PlayerInGame | None = None
        self.in_lineup = False
        self.is_injured = False
        self.pitcher_fatigue = (
            PitcherFatigue(stamina=self.skills["stamina"])
            if self.record.is_pitcher()
            else None
        )
        self.player_energy = (
            PositionPlayerFatigue(durability=self.skills["durability"])
            if not self.record.is_pitcher()
            else None
        )
        self.is_starter: bool = False  # Default to not a starting pitcher
        self.bullpen_role: str | None = (
            None  # Set at game start from bullpen_roles table
        )
        self.rate_player()

    def __str__(self):
        return f"<Player {self.name}>"

    @property
    def current_position(self) -> str | None:
        return self._current_position

    @current_position.setter
    def current_position(self, pos: str | None) -> None:
        self._current_position = pos
        if pos is not None:
            if pos not in self.fielding_by_position:
                self.fielding_by_position[pos] = FieldingStats()
            # Redirect game_stats.fielding to the active position's bucket
            self.game_stats.fielding = self.fielding_by_position[pos]

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    def is_rated(self) -> bool:
        return hasattr(self, "ratings")

    def rate_player(self):
        self.ratings = PlayerEvaluator.rate_player(self.record.skills, self.throws)

    def init_game_stats(self):
        """
        Reset the stats.
        """
        self.game_stats = stats.GameStats()
        self.fielding_by_position = {}

    @classmethod
    def from_record(cls, record: PlayerRecord):
        p = cls(record)
        p.rate_player()
        return p

    def get_effective_stat(self, base_value: int) -> int:
        """Get stat value modified by fatigue."""
        if self.pitcher_fatigue:
            modifier = self.pitcher_fatigue.get_stat_modifier()
        else:
            modifier = self.player_energy.get_stat_modifier()
        return int(base_value * modifier)

    def apply_fatigue_to_ratings(self):
        """Re-rate player with fatigue-adjusted skills."""
        if self.pitcher_fatigue:
            modifier = self.pitcher_fatigue.get_stat_modifier()
        elif self.player_energy:
            modifier = self.player_energy.get_stat_modifier()
        else:
            return

        fatigued_skills = {}
        for skill, value in self.skills.as_dict().items():
            adjusted = int(value * modifier)
            fatigued_skills[skill] = max(1, min(100, adjusted))

        fatigued_skills_obj = PlayerSkills(**fatigued_skills)
        self.ratings = PlayerEvaluator.rate_player(fatigued_skills_obj, self.throws)
