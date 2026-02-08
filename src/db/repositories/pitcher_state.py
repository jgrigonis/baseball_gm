# src/db/repositories/pitcher_state.py
"""
Repository for pitcher energy and rest state.

This table tracks pitcher fatigue across games and is used for:
- Determining starting energy levels based on rest days
- Tracking pitch counts from previous appearances
- Managing pitcher availability and scheduling

Updates:
- After each game (save final energy and pitch count)

Queries:
- Before game start (get energy, apply recovery based on rest days)
- During roster/lineup decisions (check pitcher availability)
"""

from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass

BASE_RECOVERY_RATE = 0.12
MIN_ENERGY_STARTER = 0.75


@dataclass
class PitcherState:
    """Pitcher's current energy state and recent activity."""

    player_id: str
    current_energy: float
    last_game_date: Optional[date] = None
    last_pitch_count: Optional[int] = None

    @property
    def is_fresh(self) -> bool:
        """Check if pitcher is at full energy."""
        return self.current_energy >= 1.0

    @property
    def days_since_last_game(self) -> Optional[int]:
        """Calculate days of rest since last appearance."""
        if not self.last_game_date:
            return None
        today = date.today()
        return (today - self.last_game_date).days


class PitcherStateRepository:
    """Repository for managing pitcher energy and rest."""

    def __init__(self, conn):
        self.conn = conn

    def get(self, player_id: str) -> Optional[PitcherState]:
        """
        Get pitcher's current state.

        Args:
            player_id: Player's unique ID

        Returns:
            PitcherState if exists, None if pitcher has no history
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT player_id, current_energy, last_game_date, last_pitch_count
            FROM pitcher_state
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

        return PitcherState(
            player_id=row[0],
            current_energy=row[1],
            last_game_date=last_game_date,
            last_pitch_count=row[3],
        )

    @staticmethod
    def calculate_recovery_rate(recovery_skill: int) -> float:
        """
        Calculate daily recovery rate based on pitcher's recovery skill.

        Recovery skill -> Daily rate:
        100 -> 0.24 (150% of base)
        75  -> 0.208 (130% of base)
        60  -> 0.192 (120% of base)
        50  -> 0.16 (100% base)
        30  -> 0.12 (75% of base)
        1   -> 0.10 (62.5% of base)

        Args:
            recovery_skill: Pitcher's recovery skill (1-100)

        Returns:
            Daily recovery rate (0.0-1.0)
        """
        # Base rate at skill=50
        base_rate = BASE_RECOVERY_RATE

        # Scale factor: skill affects rate with diminishing returns
        # At 100: 1.5x base (0.24)
        # At 50: 1.0x base (0.16)
        # At 1: 0.625x base (0.10)

        # Use a power curve for diminishing returns at high skills
        normalized_skill = (recovery_skill - 50) / 50  # -0.98 to 1.0
        multiplier = 1.0 + (normalized_skill * 0.5)  # 0.51 to 1.5

        return base_rate * multiplier

    def get_with_recovery(
        self,
        player_id: str,
        game_date: date,
        recovery_skill: int = 50,  # Pass the actual recovery skill
    ) -> PitcherState:
        """
        Get pitcher state with automatic recovery applied based on rest days.

        If pitcher has no history, returns fresh state at 100% energy. (1.0)

        Args:
            player_id: Player's unique ID
            game_date: Date of the upcoming game (from season schedule)
            recovery_skill: Pitcher's recovery skill (1-100, default: 50)

        Returns:
            PitcherState with recovery applied
        """
        state = self.get(player_id)

        # No history - pitcher is fresh
        if not state:
            return PitcherState(
                player_id=player_id,
                current_energy=1.0,
                last_game_date=None,
                last_pitch_count=None,
            )

        # Fix bad data - if energy is > 10, assume it's on 0-100 scale
        if state.current_energy > 10.0:
            state.current_energy = state.current_energy / 100.0
        # Fix bad data - if energy is still > 1, assume it's on 0-10 scale
        if state.current_energy > 1.0:
            state.current_energy = state.current_energy / 10.0

        # Apply recovery based on days of rest
        if state.last_game_date:
            days_rest = (game_date - state.last_game_date).days

            # Handle bad data
            if days_rest < 0:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Data inconsistency for pitcher {player_id}: "
                    f"game date {game_date} is before last appearance {state.last_game_date}. "
                    f"Resetting pitcher to fresh state."
                )
                return PitcherState(
                    player_id=player_id,
                    current_energy=1.0,
                    last_game_date=None,
                    last_pitch_count=None,
                )

            # Calculate recovery rate based on skill
            recovery_rate = self.calculate_recovery_rate(recovery_skill)
            recovery = days_rest * recovery_rate
            state.current_energy = min(1.0, state.current_energy + recovery)

        return state

    def save(self, state: PitcherState) -> None:
        """
        Save or update pitcher state.

        Args:
            state: PitcherState to save
        """
        cursor = self.conn.cursor()

        last_game_date_str = None
        if state.last_game_date:
            # Handle both date objects and strings
            if isinstance(state.last_game_date, str):
                last_game_date_str = state.last_game_date
            else:
                last_game_date_str = state.last_game_date.isoformat()

        # Round energy to 4 decimal places to avoid floating point noise
        # Also clamp to valid range [0.0, 1.0]
        energy = max(0.0, min(1.0, round(state.current_energy, 4)))

        cursor.execute(
            """
            INSERT INTO pitcher_state (player_id, current_energy, last_game_date, last_pitch_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                current_energy = excluded.current_energy,
                last_game_date = excluded.last_game_date,
                last_pitch_count = excluded.last_pitch_count
            """,
            (state.player_id, energy, last_game_date_str, state.last_pitch_count),
        )

        self.conn.commit()

    def update_after_game(
        self, player_id: str, final_energy: float, pitch_count: int, game_date: date
    ) -> None:
        """
        Update pitcher state after a game appearance.

        Args:
            player_id: Player's unique ID
            final_energy: Energy level at end of game
            pitch_count: Total pitches thrown in game
            game_date: Date of the game
        """
        if final_energy == 1.0:
            return
        state = PitcherState(
            player_id=player_id,
            current_energy=final_energy,
            last_game_date=game_date,
            last_pitch_count=pitch_count,
        )
        self.save(state)

    def delete(self, player_id: str) -> bool:
        """
        Delete pitcher state (useful for testing or player removal).

        Args:
            player_id: Player's unique ID

        Returns:
            True if state was deleted, False if didn't exist
        """
        cursor = self.conn.cursor()

        cursor.execute("DELETE FROM pitcher_state WHERE player_id = ?", (player_id,))

        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted

    def get_available_pitchers(
        self,
        player_ids: list[str],
        game_date: date,
        min_energy: float = MIN_ENERGY_STARTER,
    ) -> list[PitcherState]:
        """
        Get all pitchers with sufficient energy for a game.

        Useful for lineup/roster decisions.

        Args:
            player_ids: List of pitcher IDs to check
            game_date: Date of the upcoming game
            min_energy: Minimum energy threshold (default: 50%)
            recovery_rate_per_day: Energy recovery per day

        Returns:
            List of PitcherStates with energy >= min_energy
        """
        available = []

        for player_id in player_ids:
            state = self.get_with_recovery(player_id, game_date)
            if state.current_energy >= min_energy:
                available.append(state)

        return available
