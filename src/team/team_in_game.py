# src/team/team_in_game.py
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

    def set_lineup(
        self,
        *,
        starting_pitcher_id: str | None = None,
        style: str = "prioritized",
        dh: bool = True,
        injured_ids: set[str] | None = None,
    ) -> None:
        """
        Set the lineup with an optional specified starting pitcher.

        Args:
            starting_pitcher_id: ID of the pitcher who will start this game (optional)
            style: Lineup optimization style
            dh: Whether to use designated hitter
        """
        self._ensure_players_rated()

        # Mark injured players before optimizer sees the roster
        if injured_ids:
            for player in self.players:
                if player.id in injured_ids:
                    player.is_injured = True

        # Apply fatigue modifications BEFORE optimizing
        for player in self.players:
            player.apply_fatigue_to_ratings()

        # Exclude injured players from the optimizer's candidate pool
        available = [p for p in self.players if not p.is_injured]

        if starting_pitcher_id:
            # Use specified starting pitcher
            self.pitcher = next(
                (p for p in self.players if p.record.id == starting_pitcher_id), None
            )

            if not self.pitcher:
                raise ValueError(
                    f"Starting pitcher {starting_pitcher_id} not found on team {self.record.name}"
                )

            # Optimizer still returns (lineup, pitcher_choice) tuple
            # But we ignore the pitcher_choice since we already set self.pitcher
            self.lineup, _ = self._optimizer(
                available, style=style, dh=dh, pitcher=self.pitcher
            )
        else:
            # Fall back to old method - optimizer picks the pitcher
            self.lineup, self.pitcher = self._optimizer(
                available,
                style=style,
                dh=dh,
            )

        self._positions = {Position(slot.position): slot.player for slot in self.lineup}
        self.batter_index = 0

        # Mark starting lineup as having started the game
        for slot in self.lineup:
            slot.player.game_stats.batting.game_started = 1
            slot.player.game_stats.batting.game_played = 1
            # set player position
            slot.player.current_position = slot.position

        # Mark starting pitcher
        if self.pitcher:
            self.pitcher.game_stats.pitching.game_started = 1
            self.pitcher.game_stats.pitching.game_played = 1
            self.pitcher.current_position = Position.PITCHER.value
            self.pitcher.is_starter = True

    @property
    def bench_players(self) -> list[PlayerInGame]:
        """Players not currently in the active lineup."""
        lineup_ids = {slot.player.id for slot in self.lineup}
        return [
            p
            for p in self.players
            if p.id not in lineup_ids
            and not p.pitcher_fatigue  # exclude pitchers
            and not p.is_injured
        ]

    @property
    def position_players(self) -> list[PlayerInGame]:
        """All non-pitcher players on the roster."""
        return [p for p in self.players if not p.pitcher_fatigue]

    @property
    def current_batter(self) -> LineupSlot:
        """Return the current batter."""
        if not self.lineup:
            raise RuntimeError("Lineup has not been set")
        return self.lineup[self.batter_index]

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

    def next_batter(self) -> LineupSlot:
        """Increment the batter index and return the next batter."""
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter

    def get_fielder(self, position: Position) -> PlayerInGame | None:
        """Get player at a position."""
        return self._positions.get(position)

    def _ensure_players_rated(self) -> None:
        for p in self.players:
            if not p.is_rated():
                # print(f"{p.record.name} throws={repr(p.throws)} record.throws={repr(p.record.throws)}")

                p.rate_player()

    def get_bench_player(self, injured: LineupSlot) -> PlayerInGame | None:
        """
        Find the best available bench player for the injured player's position.

        Rates all bench players if needed, then returns the highest rated
        at the specific position being vacated.

        Args:
            injured: The player who was injured

        Returns:
            Best available substitute, or None if bench is empty
        """
        bench = self.bench_players
        if not bench:
            return None

        # Ensure all bench players are rated
        for p in bench:
            if not p.is_rated():
                p.rate_player()

        position = injured.current_position  # e.g. "lf", "1b", "c"
        if not position:
            return max(bench, key=lambda p: p.ratings.get("ovr", 0))

        return max(bench, key=lambda p: p.ratings.get(position, 0))

    def substitute(self, outgoing: PlayerInGame, incoming: PlayerInGame) -> None:
        """
        Replace a player in the lineup with a bench player.

        Args:
            outgoing: The player leaving the game
            incoming: The replacement player
        """
        slot = next((s for s in self.lineup if s.player.id == outgoing.id), None)
        if slot is None:
            self.logger.warning(f"substitute: {outgoing.name} not found in lineup")
            return

        incoming.current_position = outgoing.current_position
        incoming.game_stats.batting.game_played = 1
        slot.player = incoming

        try:
            pos = Position(outgoing.current_position)
            self._positions[pos] = incoming
        except (ValueError, TypeError):
            pass

        outgoing.current_position = None
        self.logger.info(
            f"↔️  {incoming.name} replaces {outgoing.name} "
            f"at {incoming.current_position}"
        )

    def output_lineup_skills(self) -> str:
        """Output the starting lineup skills as a string."""
        output = "\n"
        output += PlayerTableFormatter.header_skills()
        output += "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_skills(slot.player)
            output += "\n"

        return output

    def output_lineup_ratings(self) -> str:
        """Output the starting lineup ratings as a string."""
        output = "\n"
        output += PlayerTableFormatter.header_ratings()
        output += "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_ratings(slot.player)
            output += "\n"

        return output

    def output_pitcher_ratings(self) -> str:
        """Output the current pitcher ratings as a string."""
        output = "\n"
        output += PlayerTableFormatter.hor_ratings(self.current_pitcher)
        output += "\n"
        return output

    def output_pitcher_skills(self) -> str:
        """Output the current pitcher skills as a string."""
        output = "\n"
        output += PlayerTableFormatter.hor_skills(self.current_pitcher)
        output += "\n"
        return output

    def output_batting_stats(self) -> str:
        """Output the team's batting stats as a string."""
        output = "\n"
        output += PlayerTableFormatter.horizontal_stat_header()
        output += "\n"
        for player in self.players:
            if player.game_stats.batting.plate_appearances > 0:
                output += PlayerTableFormatter.horizontal_stats(player)
                output += "\n"
        return output

    def output_pitching_stats(self) -> str:
        """Output the team's pitching stats as a string."""
        output = "\n"
        output += PlayerTableFormatter.horizontal_pitching_stat_header()
        output += "\n"
        for player in self.players:
            if player.game_stats.pitching.outs > 0:
                output += PlayerTableFormatter.horizontal_pitching_stats(player)
                output += "\n"
        return output

    def output_defensive_stats(self) -> str:
        """Output the team's defensive stats as a string."""
        output = "\n"
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

    def output_lineup_card(self) -> str:
        """
        Output the starting batting order and positions.
        """
        output = "\n"
        output += PlayerTableFormatter.lineup_card(self)
        return output

    def output_rotation_card(self) -> str:
        """Output the starting pitcher."""
        output = "\n"
        output += PlayerTableFormatter.rotation_card(self)
        return output

    def output_bullpen_card(self) -> str:
        """Output the bullpen card."""
        output = "\n"
        output += PlayerTableFormatter.bullpen_card(self)
        return output
