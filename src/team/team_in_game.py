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
from enum import Enum
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


class Position(str, Enum):
    PITCHER = "p"
    CATCHER = "c"
    FIRST_BASE = "1b"
    SECOND_BASE = "2b"
    THIRD_BASE = "3b"
    SHORTSTOP = "ss"
    LEFT_FIELD = "lf"
    CENTER_FIELD = "cf"
    RIGHT_FIELD = "rf"
    DESIGNATED_HITTER = "dh"


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
        self._positions: dict[Position, PlayerInGame] = {}
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

        self._positions = {Position(slot.position): slot.player for slot in self.lineup}

        self.batter_index = 0

    def get_fielder(self, position: Position) -> PlayerInGame | None:
        """Get player at a position."""
        return self._positions.get(position)

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

    @property
    def current_pitcher(self):
        """Return the current pitcher."""
        return self.pitcher

    @property
    def current_catcher(self) -> PlayerInGame:
        """Get the current catcher."""
        catcher = self._positions.get(Position.CATCHER)
        if catcher is None:
            raise RuntimeError("No catcher in lineup")
        return catcher
