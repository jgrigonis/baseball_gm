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
Mirrors pitcher_state: exponential approach to 1.0 so recovery is fast
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
from dataclasses import dataclass
from typing import Optional

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
    last_game_date: Optional[date] = None
    consecutive_days: int = 0
    season_games_played: int = 0

    @property
    def is_fresh(self) -> bool:
        return self.current_energy >= _RECOVERY_THRESHOLD

    @property
    def needs_rest(self) -> bool:
        """True when energy has dropped to the TIRED threshold."""
        return self.current_energy < MIN_ENERGY_AVAILABLE


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PlayerEnergyRepository:
    """Repository for managing position player energy and fatigue state."""

    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PlayerEnergyState]:
        """
        Get raw player energy state from DB (no recovery applied).

        Returns None if the player has no recorded history.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, current_energy, last_game_date,
                   consecutive_days, season_games_played
            FROM player_energy
            WHERE player_id = ?
            """,
            (player_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        last_game_date = None
        if row[2]:
            last_game_date = datetime.fromisoformat(row[2]).date()

        return PlayerEnergyState(
            player_id=row[0],
            current_energy=row[1],
            last_game_date=last_game_date,
            consecutive_days=row[3],
            season_games_played=row[4],
        )

    def get_with_recovery(
        self,
        player_id: str,
        game_date: date,
        durability: int = 50,
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
        state = self.get(player_id)

        if not state:
            return PlayerEnergyState(player_id=player_id)

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
            state.consecutive_days = 0
            state.current_energy = _apply_recovery(
                state.current_energy, days_rest, durability
            )

        return state

    def days_until_ready(
        self,
        player_id: str,
        game_date: date,
        durability: int = 50,
        threshold: float = MIN_ENERGY_AVAILABLE,
    ) -> int:
        """
        How many more rest days until the player meets the energy threshold.

        Returns 0 if they are already ready.

        Args:
            player_id:  Player's unique ID.
            game_date:  Reference date (current sim date).
            durability: Player's durability skill [1-100].
            threshold:  Minimum energy to be considered available.
        """
        state = self.get_with_recovery(player_id, game_date, durability)
        energy = state.current_energy

        if energy >= threshold:
            return 0

        rate = _daily_recovery_rate(durability)
        days = 0
        while energy < threshold and days < 365:
            energy += (1.0 - energy) * rate
            days += 1

        return days

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

    def save(self, state: PlayerEnergyState) -> None:
        """
        Upsert a player energy row.

        Energy is clamped to [0.0, 1.0] and rounded to 4 decimal places
        before storage to avoid floating-point noise accumulating over time.
        """
        cursor = self.conn.cursor()

        last_game_date_str = None
        if state.last_game_date:
            if isinstance(state.last_game_date, str):
                last_game_date_str = state.last_game_date
            else:
                last_game_date_str = state.last_game_date.isoformat()

        energy = max(0.0, min(1.0, round(state.current_energy, 4)))

        cursor.execute(
            """
            INSERT INTO player_energy
                (player_id, current_energy, last_game_date, consecutive_days, season_games_played)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                current_energy      = excluded.current_energy,
                last_game_date      = excluded.last_game_date,
                consecutive_days    = excluded.consecutive_days,
                season_games_played = excluded.season_games_played
            """,
            (
                state.player_id,
                energy,
                last_game_date_str,
                state.consecutive_days,
                state.season_games_played,
            ),
        )
        self.conn.commit()

    def update_after_game(
        self,
        player_id: str,
        final_energy: float,
        consecutive_days: int,
        season_games_played: int,
        game_date: date,
    ) -> None:
        """
        Persist position player state after a game appearance.

        Pass values directly from the PositionPlayerFatigue instance
        that ran the game.

        Args:
            player_id:           Player's unique ID.
            final_energy:        fatigue.energy at end of game.
            consecutive_days:    fatigue.consecutive_days after the game.
            season_games_played: fatigue.season_games_played after the game.
            game_date:           Date the game was played.
        """
        self.save(
            PlayerEnergyState(
                player_id=player_id,
                current_energy=final_energy,
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
            placeholders = ",".join("?" * len(player_ids))
            cursor.execute(
                f"DELETE FROM player_energy WHERE player_id IN ({placeholders})",
                player_ids,
            )
        else:
            cursor.execute("DELETE FROM player_energy")

        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def delete(self, player_id: str) -> bool:
        """Delete a single player's energy row. Returns True if a row was removed."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM player_energy WHERE player_id = ?", (player_id,))
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted


# """
# Repository for position player energy and fatigue state.

# This table tracks position player fatigue across games and is used for:
# - Determining energy levels based on rest days since last game
# - Tracking consecutive games played (drives streak penalty in PositionPlayerFatigue)
# - Managing lineup decisions and rest-day scheduling

# Updates:
# - After each game (save final energy, consecutive_games, season totals)

# Queries:
# - Before game/lineup decisions (get energy with recovery applied)
# - During roster management (check who needs a rest day)

# Recovery model
# --------------
# Mirrors pitcher_state: exponential approach to 1.0 so recovery is fast
# when a player is depleted and tapers near full energy:

#     energy += (1.0 - energy) * daily_rate

# daily_rate is derived from the player's recovery skill so that a player
# starting at 0.0 reaches 0.99 in:

#     recovery skill 100  →  3 days
#     recovery skill 50   →  4 days
#     recovery skill 1    →  5 days

# Note: a rest day also resets consecutive_games to 0, which removes the
# streak penalty in PositionPlayerFatigue.play_game().
# """

# from __future__ import annotations

# import logging
# from datetime import date, datetime
# from dataclasses import dataclass
# from typing import Optional

# logger = logging.getLogger(__name__)

# # ---------------------------------------------------------------------------
# # Recovery calibration (identical to pitcher_state for consistency)
# # ---------------------------------------------------------------------------

# _RECOVERY_THRESHOLD = 0.99
# _DAYS_AT_SKILL_MAX = 3.0   # recovery skill = 100
# _DAYS_AT_SKILL_MID = 4.0   # recovery skill = 50
# _DAYS_AT_SKILL_MIN = 5.0   # recovery skill = 1

# # Minimum energy before the AI should consider resting a player
# MIN_ENERGY_AVAILABLE = 0.40  # maps to TIRED threshold in PositionPlayerFatigue


# def _daily_recovery_rate(recovery_skill: int) -> float:
#     """
#     Fraction of remaining energy gap closed each day.

#     Piecewise linear interpolation across skill range, solved analytically:

#         rate = 1 - (1 - threshold) ^ (1 / days)

#     Examples:
#         skill=100 → rate ≈ 0.779  (full in ~3 days)
#         skill=50  → rate ≈ 0.683  (full in ~4 days)
#         skill=1   → rate ≈ 0.602  (full in ~5 days)
#     """
#     skill = max(1, min(100, recovery_skill))

#     if skill <= 50:
#         t = (skill - 1) / (50 - 1)
#         days = _DAYS_AT_SKILL_MIN + t * (_DAYS_AT_SKILL_MID - _DAYS_AT_SKILL_MIN)
#     else:
#         t = (skill - 50) / (100 - 50)
#         days = _DAYS_AT_SKILL_MID + t * (_DAYS_AT_SKILL_MAX - _DAYS_AT_SKILL_MID)

#     return 1.0 - (1.0 - _RECOVERY_THRESHOLD) ** (1.0 / days)


# def _apply_recovery(energy: float, days: int, recovery_skill: int) -> float:
#     """Apply exponential recovery over ``days`` rest days."""
#     rate = _daily_recovery_rate(recovery_skill)
#     for _ in range(days):
#         energy += (1.0 - energy) * rate
#     return max(0.0, min(1.0, energy))


# # ---------------------------------------------------------------------------
# # Data class
# # ---------------------------------------------------------------------------


# @dataclass
# class PlayerEnergyState:
#     """Position player's current energy and streak state."""

#     player_id: str
#     current_energy: float = 1.0
#     last_game_date: Optional[date] = None
#     consecutive_games: int = 0
#     season_games_played: int = 0

#     @property
#     def is_fresh(self) -> bool:
#         return self.current_energy >= _RECOVERY_THRESHOLD

#     @property
#     def needs_rest(self) -> bool:
#         """True when energy has dropped to the TIRED threshold."""
#         return self.current_energy < MIN_ENERGY_AVAILABLE


# # ---------------------------------------------------------------------------
# # Repository
# # ---------------------------------------------------------------------------


# class PlayerEnergyRepository:
#     """Repository for managing position player energy and fatigue state."""

#     def __init__(self, conn):
#         self.conn = conn

#     # ------------------------------------------------------------------
#     # Read
#     # ------------------------------------------------------------------

#     def get(self, player_id: str) -> Optional[PlayerEnergyState]:
#         """
#         Get raw player energy state from DB (no recovery applied).

#         Returns None if the player has no recorded history.
#         """
#         cursor = self.conn.cursor()
#         cursor.execute(
#             """
#             SELECT player_id, current_energy, last_game_date,
#                    consecutive_games, season_games_played
#             FROM player_energy
#             WHERE player_id = ?
#             """,
#             (player_id,),
#         )
#         row = cursor.fetchone()
#         if not row:
#             return None

#         last_game_date = None
#         if row[2]:
#             last_game_date = datetime.fromisoformat(row[2]).date()

#         return PlayerEnergyState(
#             player_id=row[0],
#             current_energy=row[1],
#             last_game_date=last_game_date,
#             consecutive_games=row[3],
#             season_games_played=row[4],
#         )

#     def get_with_recovery(
#         self,
#         player_id: str,
#         game_date: date,
#         recovery_skill: int = 50,
#     ) -> PlayerEnergyState:
#         """
#         Get player energy state with recovery applied up to game_date.

#         If the player has no history they are returned at full energy.
#         If the player sat out one or more games, consecutive_games resets to 0.

#         Args:
#             player_id:      Player's unique ID.
#             game_date:      Date of the upcoming game (from season schedule).
#             recovery_skill: Player's recovery skill [1-100].

#         Returns:
#             PlayerEnergyState with current_energy and consecutive_games
#             reflecting time elapsed since last appearance.
#         """
#         state = self.get(player_id)

#         if not state:
#             return PlayerEnergyState(player_id=player_id)

#         if not state.last_game_date:
#             state.current_energy = 1.0
#             return state

#         days_rest = (game_date - state.last_game_date).days

#         if days_rest < 0:
#             logger.warning(
#                 "Data inconsistency for player %s: game_date %s is before "
#                 "last_game_date %s. Returning fresh state.",
#                 player_id,
#                 game_date,
#                 state.last_game_date,
#             )
#             return PlayerEnergyState(player_id=player_id)

#         # Any gap means at least one rest day — reset the streak
#         if days_rest > 0:
#             state.consecutive_games = 0
#             state.current_energy = _apply_recovery(
#                 state.current_energy, days_rest, recovery_skill
#             )

#         return state

#     def days_until_ready(
#         self,
#         player_id: str,
#         game_date: date,
#         recovery_skill: int = 50,
#         threshold: float = MIN_ENERGY_AVAILABLE,
#     ) -> int:
#         """
#         How many more rest days until the player meets the energy threshold.

#         Returns 0 if they are already ready.

#         Args:
#             player_id:      Player's unique ID.
#             game_date:      Reference date (current sim date).
#             recovery_skill: Player's recovery skill [1-100].
#             threshold:      Minimum energy to be considered available.
#         """
#         state = self.get_with_recovery(player_id, game_date, recovery_skill)
#         energy = state.current_energy

#         if energy >= threshold:
#             return 0

#         rate = _daily_recovery_rate(recovery_skill)
#         days = 0
#         while energy < threshold and days < 365:
#             energy += (1.0 - energy) * rate
#             days += 1

#         return days

#     def get_players_needing_rest(
#         self,
#         player_ids: list[str],
#         game_date: date,
#         recovery_skills: dict[str, int] | None = None,
#         threshold: float = MIN_ENERGY_AVAILABLE,
#     ) -> list[PlayerEnergyState]:
#         """
#         Return players whose energy has dropped below the rest threshold.

#         Useful for the lineup AI to identify who should sit today.

#         Args:
#             player_ids:      Position player IDs to check.
#             game_date:       Date of the upcoming game.
#             recovery_skills: Optional mapping of player_id → recovery skill.
#                              Defaults to 50 for any player not in the map.
#             threshold:       Energy below which a player needs rest.

#         Returns:
#             List of PlayerEnergyStates (with recovery applied) for tired players.
#         """
#         recovery_skills = recovery_skills or {}
#         tired = []

#         for player_id in player_ids:
#             skill = recovery_skills.get(player_id, 50)
#             state = self.get_with_recovery(player_id, game_date, skill)
#             if state.current_energy < threshold:
#                 tired.append(state)

#         return tired

#     # ------------------------------------------------------------------
#     # Write
#     # ------------------------------------------------------------------

#     def save(self, state: PlayerEnergyState) -> None:
#         """
#         Upsert a player energy row.

#         Energy is clamped to [0.0, 1.0] and rounded to 4 decimal places
#         before storage to avoid floating-point noise accumulating over time.
#         """
#         cursor = self.conn.cursor()

#         last_game_date_str = None
#         if state.last_game_date:
#             if isinstance(state.last_game_date, str):
#                 last_game_date_str = state.last_game_date
#             else:
#                 last_game_date_str = state.last_game_date.isoformat()

#         energy = max(0.0, min(1.0, round(state.current_energy, 4)))

#         cursor.execute(
#             """
#             INSERT INTO player_energy
#                 (player_id, current_energy, last_game_date, consecutive_games, season_games_played)
#             VALUES (?, ?, ?, ?, ?)
#             ON CONFLICT(player_id) DO UPDATE SET
#                 current_energy      = excluded.current_energy,
#                 last_game_date      = excluded.last_game_date,
#                 consecutive_games   = excluded.consecutive_games,
#                 season_games_played = excluded.season_games_played
#             """,
#             (
#                 state.player_id,
#                 energy,
#                 last_game_date_str,
#                 state.consecutive_games,
#                 state.season_games_played,
#             ),
#         )
#         self.conn.commit()

#     def update_after_game(
#         self,
#         player_id: str,
#         final_energy: float,
#         consecutive_games: int,
#         season_games_played: int,
#         game_date: date,
#     ) -> None:
#         """
#         Persist position player state after a game appearance.

#         Pass values directly from the PositionPlayerFatigue instance
#         that ran the game.

#         Args:
#             player_id:           Player's unique ID.
#             final_energy:        fatigue.energy at end of game.
#             consecutive_games:   fatigue.consecutive_games after the game.
#             season_games_played: fatigue.season_games_played after the game.
#             game_date:           Date the game was played.
#         """
#         self.save(
#             PlayerEnergyState(
#                 player_id=player_id,
#                 current_energy=final_energy,
#                 last_game_date=game_date,
#                 consecutive_games=consecutive_games,
#                 season_games_played=season_games_played,
#             )
#         )

#     def clear_season(self, player_ids: list[str] | None = None) -> int:
#         """
#         Reset energy state at the end of a season.

#         If player_ids is provided, only those players are reset.
#         Otherwise all rows are cleared.

#         Returns the number of rows affected.
#         """
#         cursor = self.conn.cursor()

#         if player_ids is not None:
#             placeholders = ",".join("?" * len(player_ids))
#             cursor.execute(
#                 f"DELETE FROM player_energy WHERE player_id IN ({placeholders})",
#                 player_ids,
#             )
#         else:
#             cursor.execute("DELETE FROM player_energy")

#         deleted = cursor.rowcount
#         self.conn.commit()
#         return deleted

#     def delete(self, player_id: str) -> bool:
#         """Delete a single player's energy row. Returns True if a row was removed."""
#         cursor = self.conn.cursor()
#         cursor.execute("DELETE FROM player_energy WHERE player_id = ?", (player_id,))
#         deleted = cursor.rowcount > 0
#         self.conn.commit()
#         return deleted
