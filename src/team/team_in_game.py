"""The TeamInGame class.

Owns:
players: list[PlayerInGame]
lineup: list[LineupSlot]
pitcher
batter_index
lineup selection logic
batter iteration

Does NOT:
create players
load CSVs
generate randomness (except strategic decisions)

"""

__author__ = "josh"
from typing import Callable

from src.player.player_in_game import PlayerInGame
from src.team.lineup_optimizer import LineupOptimizer
from src.team.lineup_slot import LineupSlot
from src.team.team_record import TeamRecord
from src.util.logger import logging

OptimizeFn = Callable[
    [list[PlayerInGame], str, bool],
    tuple[list[LineupSlot], PlayerInGame | None],
]


class TeamInGame:
    players: list[PlayerInGame]
    lineup: list[LineupSlot]
    pitcher: PlayerInGame | None
    batter_index: int

    def __init__(
        self,
        record: TeamRecord,
        *,
        optimizer: OptimizeFn = LineupOptimizer.optimize,
    ):
        self.record = record
        self.players = [PlayerInGame(p) for p in record.players]
        self._optimizer = optimizer
        self.lineup: list[LineupSlot] = []
        self.pitcher: PlayerInGame | None = None
        self.batter_index: int = 0
        self.logger = logging.getLogger("details")

    @property
    def has_lineup(self) -> bool:
        return bool(self.lineup)

    def set_lineup(self, *, style: str = "prioritized", dh: bool = True) -> None:
        self._ensure_players_rated()

        self.lineup, self.pitcher = self._optimizer(
            self.players,
            style=style,
            dh=dh,
        )

        self.batter_index = 0

    def _ensure_players_rated(self) -> None:
        for p in self.players:
            if not p.is_rated():
                p.rate_player()

    @property
    def current_batter(self) -> LineupSlot:
        """Return the current batter."""
        if not self.lineup:
            raise RuntimeError("Lineup has not been set")
        return self.lineup[self.batter_index]

    def next_batter(self) -> LineupSlot:
        """Increment the batter index and return the next batter."""
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter

    def current_pitcher(self):
        """Return the current pitcher."""
        return self.pitcher
