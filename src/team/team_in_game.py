# src/team/team_in_game.py
"""The TeamInGame class."""

__author__ = "josh"
from enum import StrEnum
from collections.abc import Callable

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


class Position(StrEnum):
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
        logger=None,
    ):
        self.record = record
        self.players = [PlayerInGame(p) for p in record.players]
        self._optimizer = optimizer
        self.lineup: list[LineupSlot] = []
        self.pitcher: PlayerInGame | None = None
        self._positions: dict[Position, PlayerInGame] = {}
        self.batter_index: int = 0
        self.logger = logger or logging.getLogger("game.details")

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
        restrict_to_ids: set[str] | None = None,
        saved_lineup: list[dict] | None = None,
    ) -> None:
        """
        Set the lineup for the game.

        Args:
            starting_pitcher_id: ID of the starting pitcher (from rotation)
            style: Lineup optimizer style (used for AI / gap-fill)
            dh: Whether to use a DH slot
            injured_ids: Player IDs currently on the IL — excluded from lineup
            restrict_to_ids: Eligible player IDs (26man, or 26man+40man for blitz).
                             None means all roster players are eligible.
            saved_lineup: Human GM's saved lineup from gm_lineup_preferences.
                         List of {player_id, batting_order, position} dicts.
                         If provided, used as-is; injured/ineligible players are
                         skipped and the optimizer fills any gaps.
        """
        self._ensure_players_rated()

        # Mark injured players
        if injured_ids:
            for player in self.players:
                if player.id in injured_ids:
                    player.is_injured = True

        # Apply fatigue modifications before optimizing
        for player in self.players:
            player.apply_fatigue_to_ratings()

        # Build the eligible pool: not injured, within roster eligibility
        available = [
            p
            for p in self.players
            if not p.is_injured and (restrict_to_ids is None or p.id in restrict_to_ids)
        ]

        # Set starting pitcher (from rotation — independent of lineup)
        if starting_pitcher_id:
            self.pitcher = next(
                (p for p in self.players if p.record.id == starting_pitcher_id), None
            )
            if not self.pitcher:
                self.logger.warning(
                    f"Starting pitcher {starting_pitcher_id} not found on {self.record.name}"
                )

        if saved_lineup:
            self._set_lineup_from_saved(saved_lineup, available, style, dh)
        else:
            self._set_lineup_from_optimizer(available, style, dh)

        self._positions = {Position(slot.position): slot.player for slot in self.lineup}
        self.batter_index = 0

        # Mark starting stats
        for slot in self.lineup:
            slot.player.game_stats.batting.game_started = 1
            slot.player.game_stats.batting.game_played = 1
            slot.player.current_position = slot.position

        if self.pitcher:
            self.pitcher.game_stats.pitching.game_started = 1
            self.pitcher.game_stats.pitching.game_played = 1
            self.pitcher.current_position = Position.PITCHER.value
            self.pitcher.is_starter = True

    def _set_lineup_from_saved(
        self,
        saved: list[dict],
        available: list[PlayerInGame],
        style: str,
        dh: bool,
    ) -> None:
        """
        Build lineup from GM's saved preferences.
        When a saved player is injured/ineligible, immediately find the best
        available replacement for their specific position so no defensive
        position is left uncovered.
        """
        available_by_id = {p.id: p for p in available}
        # Pitcher doesn't bat
        if self.pitcher:
            available_by_id.pop(self.pitcher.id, None)

        lineup_slots: list[LineupSlot] = []
        used_ids: set[str] = set()

        def best_for_position(pos: str) -> PlayerInGame | None:
            """Pick the highest-rated available player for a given position."""
            candidates = [p for p in available_by_id.values() if p.id not in used_ids]
            if not candidates:
                return None
            return max(candidates, key=lambda p: p.ratings.get(pos, 0))

        for slot in sorted(saved, key=lambda s: s["batting_order"]):
            pid = slot["player_id"]
            position = slot.get("position") or "dh"
            player = available_by_id.get(pid)

            if not player:
                # Injured or ineligible — find best replacement for their position
                sub = best_for_position(position)
                if sub:
                    self.logger.info(
                        f"Saved lineup: {pid} unavailable, subbing {sub.id} at {position}"
                    )
                    lineup_slots.append(LineupSlot(sub, position))
                    used_ids.add(sub.id)
                else:
                    self.logger.info(
                        f"Saved lineup: {pid} unavailable, no sub found for {position}"
                    )
                continue

            # Guard: player may have already been used as a sub for an earlier injured slot
            if pid in used_ids:
                sub = best_for_position(position)
                if sub:
                    self.logger.info(
                        f"Saved lineup: {pid} already used, subbing {sub.id} at {position}"
                    )
                    lineup_slots.append(LineupSlot(sub, position))
                    used_ids.add(sub.id)
                continue

            lineup_slots.append(LineupSlot(player, position))
            used_ids.add(pid)

        # Fill any defensive position the saved lineup no longer covers — e.g.
        # its player was traded away, which deletes their saved slot outright.
        required = [
            pos.value
            for pos in Position
            if pos is not Position.PITCHER
            and (dh or pos is not Position.DESIGNATED_HITTER)
        ]
        filled = {slot.position for slot in lineup_slots}
        for position in required:
            if position in filled:
                continue
            sub = best_for_position(position)
            if not sub:
                break
            self.logger.info(f"Saved lineup has no {position}, filling with {sub.id}")
            lineup_slots.append(LineupSlot(sub, position))
            used_ids.add(sub.id)
            filled.add(position)

        # Fill any remaining batting order gaps (shouldn't happen often)
        needed = 9 if dh else 8
        gap_count = needed - len(lineup_slots)
        if gap_count > 0:
            remaining = [
                p
                for p in available
                if p.id not in used_ids
                and (self.pitcher is None or p.id != self.pitcher.id)
            ]
            if remaining:
                self.logger.info(
                    f"Saved lineup has {gap_count} remaining gap(s), filling with optimizer"
                )
                try:
                    gap_lineup, _ = self._optimizer(
                        remaining,
                        style=style,
                        dh=True,
                        pitcher=self.pitcher,
                    )
                    valid_gap = [
                        s
                        for s in gap_lineup[:gap_count]
                        if s is not None and s.player is not None
                    ]
                    lineup_slots.extend(valid_gap)
                except Exception as e:
                    self.logger.warning(f"Gap-fill optimizer failed: {e}")

        # Safety check — if we couldn't fill all slots, fall back to optimizer
        valid_slots = [
            s for s in lineup_slots if s is not None and s.player is not None
        ]
        missing = set(required) - {slot.position for slot in valid_slots}
        if len(valid_slots) < (9 if dh else 8) or missing:
            self.logger.warning(
                f"Saved lineup only produced {len(valid_slots)} valid slots "
                f"(missing {sorted(missing)}), falling back to optimizer"
            )
            self._set_lineup_from_optimizer(available, style, dh)
        else:
            self.lineup = valid_slots

    def _set_lineup_from_optimizer(
        self,
        available: list[PlayerInGame],
        style: str,
        dh: bool,
    ) -> None:
        """Full optimizer-driven lineup — used for AI teams and when no saved lineup."""
        if self.pitcher:
            lineup, _ = self._optimizer(
                available, style=style, dh=dh, pitcher=self.pitcher
            )
        else:
            lineup, self.pitcher = self._optimizer(available, style=style, dh=dh)
        self.lineup = lineup

    @property
    def bench_players(self) -> list[PlayerInGame]:
        """Players not currently in the active lineup."""
        lineup_ids = {slot.player.id for slot in self.lineup}
        return [
            p
            for p in self.players
            if p.id not in lineup_ids and not p.pitcher_fatigue and not p.is_injured
        ]

    @property
    def position_players(self) -> list[PlayerInGame]:
        """All non-pitcher players on the roster."""
        return [p for p in self.players if not p.pitcher_fatigue]

    @property
    def current_batter(self) -> LineupSlot:
        if not self.lineup:
            raise RuntimeError("Lineup has not been set")
        return self.lineup[self.batter_index]

    @property
    def current_pitcher(self):
        return self.pitcher

    @property
    def current_catcher(self) -> PlayerInGame:
        catcher = self._positions.get(Position.CATCHER)
        if catcher is None:
            raise RuntimeError("No catcher in lineup")
        return catcher

    @property
    def current_first_baseman(self) -> PlayerInGame:
        first_base = self._positions.get(Position.FIRST_BASE)
        if first_base is None:
            raise RuntimeError("No first_base in lineup")
        return first_base

    @property
    def current_second_baseman(self) -> PlayerInGame:
        second_base = self._positions.get(Position.SECOND_BASE)
        if second_base is None:
            raise RuntimeError("No second_base in lineup")
        return second_base

    @property
    def current_shortstop(self) -> PlayerInGame:
        shortstop = self._positions.get(Position.SHORTSTOP)
        if shortstop is None:
            raise RuntimeError("No shortstop in lineup")
        return shortstop

    @property
    def current_third_baseman(self) -> PlayerInGame:
        third_base = self._positions.get(Position.THIRD_BASE)
        if third_base is None:
            raise RuntimeError("No third_base in lineup")
        return third_base

    @property
    def current_left_fielder(self) -> PlayerInGame:
        left_field = self._positions.get(Position.LEFT_FIELD)
        if left_field is None:
            raise RuntimeError("No left_field in lineup")
        return left_field

    @property
    def current_right_fielder(self) -> PlayerInGame:
        right_field = self._positions.get(Position.RIGHT_FIELD)
        if right_field is None:
            raise RuntimeError("No right_field in lineup")
        return right_field

    @property
    def current_center_fielder(self) -> PlayerInGame:
        center_field = self._positions.get(Position.CENTER_FIELD)
        if center_field is None:
            raise RuntimeError("No center_field in lineup")
        return center_field

    @property
    def current_dh(self) -> PlayerInGame:
        dh = self._positions.get(Position.DESIGNATED_HITTER)
        if dh is None:
            raise RuntimeError("No dh in lineup")
        return dh

    def next_batter(self) -> LineupSlot:
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter

    def get_fielder(self, position: Position) -> PlayerInGame | None:
        return self._positions.get(position)

    def _ensure_players_rated(self) -> None:
        for p in self.players:
            if not p.is_rated():
                p.rate_player()

    def get_bench_player(self, injured: PlayerInGame) -> PlayerInGame | None:
        bench = self.bench_players
        if not bench:
            return None
        for p in bench:
            if not p.is_rated():
                p.rate_player()
        position = injured.current_position
        if not position:
            return max(bench, key=lambda p: p.ratings.get("ovr", 0))
        return max(bench, key=lambda p: p.ratings.get(position, 0))

    def substitute(self, outgoing: PlayerInGame, incoming: PlayerInGame) -> None:
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
        except ValueError, TypeError:
            pass
        outgoing.current_position = None
        self.logger.debug(
            f"↔️  {incoming.name} replaces {outgoing.name} at {incoming.current_position}"
        )

    def output_lineup_skills(self) -> str:
        output = "\n" + PlayerTableFormatter.header_skills() + "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_skills(slot.player) + "\n"
        return output

    def output_lineup_ratings(self) -> str:
        output = "\n" + PlayerTableFormatter.header_ratings() + "\n"
        for slot in self.lineup:
            output += PlayerTableFormatter.hor_ratings(slot.player) + "\n"
        return output

    def output_pitcher_ratings(self) -> str:
        return "\n" + PlayerTableFormatter.hor_ratings(self.current_pitcher) + "\n"

    def output_pitcher_skills(self) -> str:
        return "\n" + PlayerTableFormatter.hor_skills(self.current_pitcher) + "\n"

    def output_batting_stats(self) -> str:
        output = "\n" + PlayerTableFormatter.horizontal_stat_header() + "\n"
        for player in self.players:
            if player.game_stats.batting.plate_appearances > 0:
                output += PlayerTableFormatter.horizontal_stats(player) + "\n"
        return output

    def output_pitching_stats(self) -> str:
        output = "\n" + PlayerTableFormatter.horizontal_pitching_stat_header() + "\n"
        for player in self.players:
            if player.game_stats.pitching.outs > 0:
                output += PlayerTableFormatter.horizontal_pitching_stats(player) + "\n"
        return output

    def output_defensive_stats(self) -> str:
        output = "\n" + PlayerTableFormatter.horizontal_defensive_stat_header() + "\n"
        for player in self.players:
            if (
                player.game_stats.fielding.assists > 0
                or player.game_stats.fielding.putouts > 0
                or player.game_stats.fielding.errors > 0
            ):
                output += PlayerTableFormatter.horizontal_defensive_stats(player) + "\n"
        return output

    def output_lineup_card(self) -> str:
        return "\n" + PlayerTableFormatter.lineup_card(self)

    def output_rotation_card(self) -> str:
        return "\n" + PlayerTableFormatter.rotation_card(self)

    def output_bullpen_card(self) -> str:
        return "\n" + PlayerTableFormatter.bullpen_card(self)
