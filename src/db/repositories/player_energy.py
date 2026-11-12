# src/db/repositories/player_energy.py
"""
src/db/repositories/player_energy.py

Repository for position player energy and fatigue state.

This table tracks position player fatigue across games and is used for:
- Determining energy levels based on rest days since last game
- Tracking consecutive days played (drives streak penalty in PositionPlayerFatigue)
- Managing lineup decisions and rest-day scheduling

Updates:
- After each game (save final energy, consecutive_days, season totals)

Queries:
- Before game/lineup decisions (get energy with recovery applied)
- During roster management (check who needs a rest day)

Recovery model
--------------
Exponential approach to 1.0 so recovery is fast
when a player is depleted and tapers near full energy:

    energy += (1.0 - energy) * daily_rate

daily_rate is derived from the player's durability skill so that a player
starting at 0.0 reaches 0.99 in:

    durability 100  →  3 days
    durability 50   →  4 days
    durability 1    →  5 days

durability also controls how fast energy drains in PositionPlayerFatigue,
so a high-durability player both loses energy more slowly and recovers faster.

A gap in the schedule (off-day or rest day) resets consecutive_days to 0,
since the streak tracks unbroken days in the lineup.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from dataclasses import dataclass, replace
from collections.abc import Iterable

from src.util.clamp import clamp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recovery calibration
# ---------------------------------------------------------------------------

_RECOVERY_THRESHOLD = 0.99
_DAYS_AT_DURABILITY_MAX = 3.0  # durability = 100
_DAYS_AT_DURABILITY_MID = 4.0  # durability = 50
_DAYS_AT_DURABILITY_MIN = 5.0  # durability = 1

# Minimum energy before the AI should consider resting a player
MIN_ENERGY_AVAILABLE = 0.40  # maps to TIRED threshold in PositionPlayerFatigue


def _daily_recovery_rate(durability: int) -> float:
    """
    Fraction of remaining energy gap closed each day.

    Piecewise linear interpolation across durability range, solved analytically:

        rate = 1 - (1 - threshold) ^ (1 / days)

    Examples:
        durability=100 → rate ≈ 0.779  (full in ~3 days)
        durability=50  → rate ≈ 0.683  (full in ~4 days)
        durability=1   → rate ≈ 0.602  (full in ~5 days)
    """
    d = max(1, min(100, durability))

    if d <= 50:
        t = (d - 1) / (50 - 1)
        days = _DAYS_AT_DURABILITY_MIN + t * (
            _DAYS_AT_DURABILITY_MID - _DAYS_AT_DURABILITY_MIN
        )
    else:
        t = (d - 50) / (100 - 50)
        days = _DAYS_AT_DURABILITY_MID + t * (
            _DAYS_AT_DURABILITY_MAX - _DAYS_AT_DURABILITY_MID
        )

    return 1.0 - (1.0 - _RECOVERY_THRESHOLD) ** (1.0 / days)


def _apply_recovery(energy: float, days: int, durability: int) -> float:
    """Apply exponential recovery over ``days`` rest days."""
    rate = _daily_recovery_rate(durability)
    for _ in range(days):
        energy += (1.0 - energy) * rate
    return max(0.0, min(1.0, energy))


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class PlayerEnergyState:
    """Position player's current energy and streak state."""

    player_id: str
    current_energy: float = 1.0
    max_energy: float = 1.0
    last_game_date: date | None = None
    consecutive_days: int = 0
    season_games_played: int = 0

    # Never used
    # @property
    # def is_fresh(self) -> bool:
    #     return self.current_energy >= _RECOVERY_THRESHOLD

    @property
    def needs_rest(self) -> bool:
        """True when energy has dropped to the TIRED threshold."""
        return self.current_energy < MIN_ENERGY_AVAILABLE


def recover_player_energy(
    state: PlayerEnergyState | None,
    player_id: str,
    game_date: date,
    durability: int = 50,
    rate_mult: float = 1.0,
) -> PlayerEnergyState:
    """
    Return a copy of a stored energy state with recovery applied up to game_date.

    ``state`` is the raw row as returned by ``PlayerEnergyRepository.get`` or
    ``get_many`` (None when the player has no history). It is not modified.
    ``rate_mult`` speeds or slows the daily recovery: his team's Facilities
    (src/league/budget.py facilities_recovery).
    """
    if not state:
        return PlayerEnergyState(player_id=player_id)

    state = replace(state)
    if not state.last_game_date:
        state.current_energy = 1.0
        return state

    days_rest = (game_date - state.last_game_date).days

    if days_rest < 0:
        logger.warning(
            "Data inconsistency for player %s: game_date %s is before "
            "last_game_date %s. Returning fresh state.",
            player_id,
            game_date,
            state.last_game_date,
        )
        return PlayerEnergyState(player_id=player_id)

    if days_rest > 0:
        if days_rest >= 2:
            state.consecutive_days = 0

        # Exponential approach toward max_energy
        rate = min(0.95, _daily_recovery_rate(durability) * rate_mult)
        energy = state.current_energy
        for _ in range(days_rest):
            energy += (state.max_energy - energy) * rate
        state.current_energy = max(0.0, min(state.max_energy, energy))

        # Cap slow regeneration
        state.max_energy = min(1.0, state.max_energy + 0.003 * days_rest)

        # state.current_energy = _apply_recovery(
        #     state.current_energy, days_rest, durability
        # )

    return state


def _row_to_state(row) -> PlayerEnergyState:
    last_game_date = (
        datetime.fromisoformat(row["last_game_date"]).date()
        if row["last_game_date"]
        else None
    )

    return PlayerEnergyState(
        player_id=row["player_id"],
        current_energy=row["current_energy"],
        max_energy=row["max_energy"],
        last_game_date=last_game_date,
        consecutive_days=row["consecutive_days"],
        season_games_played=row["season_games_played"],
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PlayerEnergyRepository:
    """Repository for managing position player energy and fatigue state."""

    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> PlayerEnergyState | None:
        """
        Get raw player energy state from DB (no recovery applied).

        Returns None if the player has no recorded history.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, current_energy, max_energy, last_game_date,
                   consecutive_days, season_games_played
            FROM player_energy
            WHERE player_id = %s AND league_id = %s
            """,
            (player_id, self.league_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_state(row)

    def get_many(self, player_ids: Iterable[str]) -> dict[str, PlayerEnergyState]:
        """
        Fetch raw energy states for many players in one query.

        Returns a dict keyed by player_id. Players with no recorded history
        are left out.
        """
        player_ids = list(player_ids)
        if not player_ids:
            return {}
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, current_energy, max_energy, last_game_date,
                   consecutive_days, season_games_played
            FROM player_energy
            WHERE player_id = ANY(%s) AND league_id = %s
            """,
            (player_ids, self.league_id),
        )
        return {row["player_id"]: _row_to_state(row) for row in cursor.fetchall()}

    def get_with_recovery(
        self,
        player_id: str,
        game_date: date,
        durability: int = 50,
        rate_mult: float = 1.0,
    ) -> PlayerEnergyState:
        """
        Get player energy state with recovery applied up to game_date.

        If the player has no history they are returned at full energy.
        Any gap between last_game_date and game_date resets consecutive_days
        to 0 and applies energy recovery for each day elapsed.

        Args:
            player_id:  Player's unique ID.
            game_date:  Date of the upcoming game (from season schedule).
            durability: Player's durability skill [1-100].

        Returns:
            PlayerEnergyState with current_energy and consecutive_days
            reflecting time elapsed since last appearance.
        """
        return recover_player_energy(
            self.get(player_id), player_id, game_date, durability, rate_mult
        )

    def get_many_with_recovery(
        self,
        durabilities: dict[str, int],
        game_date: date,
        rate_mults: dict[str, float] | None = None,
    ) -> dict[str, PlayerEnergyState]:
        """
        Batch version of get_with_recovery, using one query.

        Args:
            durabilities: Mapping of player_id → durability skill. Every
                          player in it gets an entry in the result, in the
                          same order.
            game_date:    Date of the upcoming game.
            rate_mults:   Optional player_id → recovery speed (Facilities);
                          missing players recover at the normal rate.
        """
        raw = self.get_many(durabilities)
        rate_mults = rate_mults or {}
        return {
            pid: recover_player_energy(
                raw.get(pid), pid, game_date, durability, rate_mults.get(pid, 1.0)
            )
            for pid, durability in durabilities.items()
        }

    # THIS CODE IS NOT USED, BUT MAY BE USEFUL
    # def days_until_ready(
    #     self,
    #     player_id: str,
    #     game_date: date,
    #     durability: int = 50,
    #     threshold: float = MIN_ENERGY_AVAILABLE,
    # ) -> int:
    #     """
    #     How many more rest days until the player meets the energy threshold.

    #     Returns 0 if they are already ready.

    #     Args:
    #         player_id:  Player's unique ID.
    #         game_date:  Reference date (current sim date).
    #         durability: Player's durability skill [1-100].
    #         threshold:  Minimum energy to be considered available.
    #     """
    #     state = self.get_with_recovery(player_id, game_date, durability)
    #     energy = state.current_energy

    #     if energy >= threshold:
    #         return 0

    #     rate = _daily_recovery_rate(durability)
    #     days = 0
    #     while energy < threshold and days < 365:
    #         energy += (1.0 - energy) * rate
    #         days += 1

    #     return days
    # THIS CODE IS NOT USED, BUT MAY BE USEFUL

    # We aren't using this code anywhere, we need to
    def get_players_needing_rest(
        self,
        player_ids: list[str],
        game_date: date,
        durabilities: dict[str, int] | None = None,
        threshold: float = MIN_ENERGY_AVAILABLE,
    ) -> list[PlayerEnergyState]:
        """
        Return players whose energy has dropped below the rest threshold.

        Useful for the lineup AI to identify who should sit today.

        Args:
            player_ids:   Position player IDs to check.
            game_date:    Date of the upcoming game.
            durabilities: Optional mapping of player_id → durability skill.
                          Defaults to 50 for any player not in the map.
            threshold:    Energy below which a player needs rest.

        Returns:
            List of PlayerEnergyStates (with recovery applied) for tired players.
        """
        durabilities = durabilities or {}
        tired = []

        for player_id in player_ids:
            d = durabilities.get(player_id, 50)
            state = self.get_with_recovery(player_id, game_date, d)
            if state.current_energy < threshold:
                tired.append(state)

        return tired

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_player_energy(self, state: PlayerEnergyState) -> None:
        """
        Upsert a player energy row.

        Energy is clamped to [0.0, 1.0] and rounded to 4 decimal places
        before storage to avoid floating-point noise accumulating over time.
        """
        self.save_many([state])

    def save_many(self, states: Iterable[PlayerEnergyState]) -> None:
        """Upsert many player energy rows in one batch (see save_player_energy)."""
        params = [self._save_params(state) for state in states]
        if not params:
            return
        cursor = self.conn.cursor()
        cursor.executemany(
            """
            INSERT INTO player_energy
                (player_id, league_id, current_energy, max_energy, last_game_date, consecutive_days, season_games_played)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(player_id, league_id) DO UPDATE SET
                current_energy       = excluded.current_energy,
                max_energy           = excluded.max_energy,
                last_game_date       = excluded.last_game_date,
                consecutive_days     = excluded.consecutive_days,
                season_games_played  = excluded.season_games_played
            """,
            params,
        )

    def _save_params(self, state: PlayerEnergyState) -> tuple:
        last_game_date_str = None
        if state.last_game_date:
            if isinstance(state.last_game_date, str):
                last_game_date_str = state.last_game_date
            else:
                last_game_date_str = state.last_game_date.isoformat()

        return (
            state.player_id,
            self.league_id,
            clamp(state.current_energy, 0.0, 1.0, 4),
            state.max_energy,
            last_game_date_str,
            state.consecutive_days,
            state.season_games_played,
        )

    def update_after_game(
        self,
        player_id: str,
        final_energy: float,
        max_energy: float,
        consecutive_days: int,
        season_games_played: int,
        game_date: date,
    ) -> None:
        """
        Persist position player state after a game appearance.

        Pass values directly from the PositionPlayerFatigue instance
        that ran the game.

        Args:
            player_id:            Player's unique ID.
            final_energy:         fatigue.energy at end of game.
            consecutive_days:     fatigue.consecutive_days after the game.
            season_games_played:  fatigue.season_games_played after the game.
            game_date:            Date the game was played.
        """
        self.save_player_energy(
            PlayerEnergyState(
                player_id=player_id,
                current_energy=final_energy,
                max_energy=max_energy,
                last_game_date=game_date,
                consecutive_days=consecutive_days,
                season_games_played=season_games_played,
            )
        )

    def clear_season(self, player_ids: list[str] | None = None) -> int:
        """
        Reset energy state at the end of a season.

        If player_ids is provided, only those players are reset.
        Otherwise all rows are cleared.

        Returns the number of rows affected.
        """
        cursor = self.conn.cursor()

        if player_ids is not None:
            placeholders = ", ".join(["%s"] * len(player_ids))
            cursor.execute(
                f"DELETE FROM player_energy WHERE league_id = %s AND player_id IN ({placeholders})",
                [self.league_id] + list(player_ids),
            )
        else:
            cursor.execute(
                "DELETE FROM player_energy WHERE league_id = %s", (self.league_id,)
            )

        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def delete(self, player_id: str) -> bool:
        """Delete a single player's energy row. Returns True if a row was removed."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_energy WHERE player_id = %s AND league_id = %s",
            (player_id, self.league_id),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted
