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

from src.player.player_formatters import PlayerTableFormatter
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

    @property
    def current_first_baseman(self) -> PlayerInGame:
        """Get the current first basemen."""
        first_base = self._positions.get(Position.FIRST_BASE)
        if first_base is None:
            raise RuntimeError("No first_base in lineup")
        return first_base

    @property
    def current_second_baseman(self) -> PlayerInGame:
        """Get the current second basemen."""
        second_base = self._positions.get(Position.SECOND_BASE)
        if second_base is None:
            raise RuntimeError("No second_base in lineup")
        return second_base

    @property
    def current_shortstop(self) -> PlayerInGame:
        """Get the current shortstop."""
        shortstop = self._positions.get(Position.SHORTSTOP)
        if shortstop is None:
            raise RuntimeError("No shortstop in lineup")
        return shortstop

    @property
    def current_third_baseman(self) -> PlayerInGame:
        """Get the current third basemen."""
        third_base = self._positions.get(Position.THIRD_BASE)
        if third_base is None:
            raise RuntimeError("No third_base in lineup")
        return third_base

    @property
    def current_left_fielder(self) -> PlayerInGame:
        """Get the current left fielder."""
        left_field = self._positions.get(Position.LEFT_FIELD)
        if left_field is None:
            raise RuntimeError("No left_field in lineup")
        return left_field

    @property
    def current_right_fielder(self) -> PlayerInGame:
        """Get the current right fielder."""
        right_field = self._positions.get(Position.RIGHT_FIELD)
        if right_field is None:
            raise RuntimeError("No right_field in lineup")
        return right_field

    @property
    def current_center_fielder(self) -> PlayerInGame:
        """Get the current center fielder."""
        center_field = self._positions.get(Position.CENTER_FIELD)
        if center_field is None:
            raise RuntimeError("No center_field in lineup")
        return center_field

    @property
    def current_dh(self) -> PlayerInGame:
        """Get the current center fielder."""
        dh = self._positions.get(Position.DESIGNATED_HITTER)
        if dh is None:
            raise RuntimeError("No dh in lineup")
        return dh

    def output_lineup_skills(self) -> str:
        """Output the starting lineup skills as a string."""
        output = ""
        output += PlayerTableFormatter.header_skills()
        output += "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_skills(slot.player)
            output += "\n"

        return output

    def output_lineup_ratings(self) -> str:
        """Output the starting lineup ratings as a string."""
        output = ""
        output += PlayerTableFormatter.header_ratings()
        output += "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_ratings(slot.player)
            output += "\n"

        return output

    def output_pitcher_ratings(self) -> str:
        """Output the current pitcher ratings as a string."""
        output = ""
        output += PlayerTableFormatter.hor_ratings(self.current_pitcher)
        output += "\n"
        return output

    def output_pitcher_skills(self) -> str:
        """Output the current pitcher skills as a string."""
        output = ""
        output += PlayerTableFormatter.hor_skills(self.current_pitcher)
        output += "\n"
        return output

    def output_batting_stats(self) -> str:
        """Output the team's batting stats as a string."""
        output = ""
        output += PlayerTableFormatter.horizontal_stat_header()
        output += "\n"
        for player in self.players:
            if player.game_stats.batting.plate_appearances > 0:
                output += PlayerTableFormatter.horizontal_stats(player)
                output += "\n"
        return output

    def output_pitching_stats(self) -> str:
        """Output the team's pitching stats as a string."""
        output = ""
        output += PlayerTableFormatter.horizontal_pitching_stat_header()
        output += "\n"
        for player in self.players:
            if player.game_stats.pitching.outs > 0:
                output += PlayerTableFormatter.horizontal_pitching_stats(player)
                output += "\n"
        return output

    def output_defensive_stats(self) -> str:
        """Output the team's defensive stats as a string."""
        output = ""
        output += PlayerTableFormatter.horizontal_defensive_stat_header()
        output += "\n"
        for player in self.players:
            if (
                player.game_stats.fielding.assists > 0
                or player.game_stats.fielding.putouts > 0
                or player.game_stats.fielding.errors > 0
            ):
                output += PlayerTableFormatter.horizontal_defensive_stats(player)
                output += "\n"
        return output
