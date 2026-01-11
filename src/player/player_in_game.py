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

"""

import src.stats.stats as stats

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord


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
        self.fatigue = 0
        self.in_lineup = False
        self.current_position = None
        self.is_injured = False

    def __str__(self):
        return f"<Player {self.name}>"

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    def rate_player(self):
        self.ratings = PlayerEvaluator.rate_player(self.record.skills)

    def init_game_stats(self):
        """
        Reset the stats.
        """
        self.game_stats = stats.GameStats()
