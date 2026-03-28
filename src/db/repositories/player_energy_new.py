# src/db/repositories/player_energy.py
"""
Repository for position player energy and fatigue state, scoped per league.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_RECOVERY_THRESHOLD = 0.99
_DAYS_AT_DURABILITY_MAX = 3.0
_DAYS_AT_DURABILITY_MID = 4.0
_DAYS_AT_DURABILITY_MIN = 5.0
MIN_ENERGY_AVAILABLE = 0.40


def _daily_recovery_rate(durability: int) -> float:
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
    rate = _daily_recovery_rate(durability)
    for _ in range(days):
        energy += (1.0 - energy) * rate
    return max(0.0, min(1.0, energy))


@dataclass
class PlayerEnergyState:
    player_id: str
    current_energy: float = 1.0
    max_energy: float = 1.0
    last_game_date: Optional[date] = None
    consecutive_days: int = 0
    season_games_played: int = 0

    @property
    def is_fresh(self) -> bool:
        return self.current_energy >= _RECOVERY_THRESHOLD

    @property
    def needs_rest(self) -> bool:
        return self.current_energy < MIN_ENERGY_AVAILABLE


class PlayerEnergyRepository:
    """Repository for managing position player energy, scoped to a single league."""

    def __init__(self, conn, league_id: str = ""):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PlayerEnergyState]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT player_id, current_energy, max_energy, last_game_date,
                      consecutive_days, season_games_played
               FROM player_energy
               WHERE player_id = ? AND league_id = ?""",
            (player_id, self.league_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        last_game_date = datetime.fromisoformat(row[3]).date() if row[3] else None
        return PlayerEnergyState(
            player_id=row[0],
            current_energy=row[1],
            max_energy=row[2],
            last_game_date=last_game_date,
            consecutive_days=row[4],
            season_games_played=row[5],
        )

    def get_with_recovery(
        self, player_id: str, game_date: date, durability: int = 50
    ) -> PlayerEnergyState:
        state = self.get(player_id)
        if not state:
            return PlayerEnergyState(player_id=player_id)
        if not state.last_game_date:
            state.current_energy = 1.0
            return state
        days_rest = (game_date - state.last_game_date).days
        if days_rest < 0:
            logger.warning(
                "Data inconsistency for player %s: game_date %s before last_game_date %s.",
                player_id,
                game_date,
                state.last_game_date,
            )
            return PlayerEnergyState(player_id=player_id)
        if days_rest > 0:
            state.consecutive_days = 0
            rate = _daily_recovery_rate(durability)
            energy = state.current_energy
            for _ in range(days_rest):
                energy += (state.max_energy - energy) * rate
            state.current_energy = max(0.0, min(state.max_energy, energy))
            state.max_energy = min(1.0, state.max_energy + 0.003 * days_rest)
        return state

    def get_players_needing_rest(
        self, player_ids, game_date, durabilities=None, threshold=MIN_ENERGY_AVAILABLE
    ):
        durabilities = durabilities or {}
        tired = []
        for player_id in player_ids:
            state = self.get_with_recovery(
                player_id, game_date, durabilities.get(player_id, 50)
            )
            if state.current_energy < threshold:
                tired.append(state)
        return tired

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, state: PlayerEnergyState) -> None:
        cursor = self.conn.cursor()
        last_game_date_str = None
        if state.last_game_date:
            last_game_date_str = (
                state.last_game_date
                if isinstance(state.last_game_date, str)
                else state.last_game_date.isoformat()
            )
        energy = max(0.0, min(1.0, round(state.current_energy, 4)))
        cursor.execute(
            """INSERT INTO player_energy
                   (player_id, league_id, current_energy, max_energy,
                    last_game_date, consecutive_days, season_games_played)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(player_id, league_id) DO UPDATE SET
                   current_energy      = excluded.current_energy,
                   max_energy          = excluded.max_energy,
                   last_game_date      = excluded.last_game_date,
                   consecutive_days    = excluded.consecutive_days,
                   season_games_played = excluded.season_games_played""",
            (
                state.player_id,
                self.league_id,
                energy,
                state.max_energy,
                last_game_date_str,
                state.consecutive_days,
                state.season_games_played,
            ),
        )
        self.conn.commit()

    def update_after_game(
        self,
        player_id,
        final_energy,
        max_energy,
        consecutive_days,
        season_games_played,
        game_date,
    ):
        self.save(
            PlayerEnergyState(
                player_id=player_id,
                current_energy=final_energy,
                max_energy=max_energy,
                last_game_date=game_date,
                consecutive_days=consecutive_days,
                season_games_played=season_games_played,
            )
        )

    def clear_season(self, player_ids=None) -> int:
        cursor = self.conn.cursor()
        if player_ids is not None:
            placeholders = ",".join("?" * len(player_ids))
            cursor.execute(
                f"DELETE FROM player_energy WHERE league_id = ? AND player_id IN ({placeholders})",
                [self.league_id] + list(player_ids),
            )
        else:
            cursor.execute(
                "DELETE FROM player_energy WHERE league_id = ?", (self.league_id,)
            )
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def delete(self, player_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_energy WHERE player_id = ? AND league_id = ?",
            (player_id, self.league_id),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted
