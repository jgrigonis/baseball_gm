"""
src/db/repositories/pitcher_state.py

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

Recovery model
--------------
Uses an exponential approach to 1.0 so recovery is fast when a pitcher
is depleted and tapers as they approach full energy:

    energy += (1.0 - energy) * daily_rate

daily_rate is derived from the pitcher's recovery skill so that a pitcher
starting at 0.0 reaches 0.99 in:

    recovery skill 100  →  4 days
    recovery skill 50   →  5 days
    recovery skill 1    →  6 days
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recovery calibration
# ---------------------------------------------------------------------------

_RECOVERY_THRESHOLD = 0.99  # "effectively full"
_DAYS_AT_SKILL_MAX = 4.0  # recovery = 100
_DAYS_AT_SKILL_MID = 5.0  # recovery = 50
_DAYS_AT_SKILL_MIN = 6.0  # recovery = 1

MIN_ENERGY_STARTER = 0.75

# Cap: slow passive regeneration
CAP_REGEN_PER_DAY = 0.004


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _daily_recovery_rate(recovery_skill: int) -> float:
    """
    Fraction of remaining energy gap closed each day.

    Piecewise linear interpolation of target days across the skill range,
    then solved analytically:

        rate = 1 - (1 - threshold) ^ (1 / days)

    Examples:
        skill=100 → rate ≈ 0.779  (full in 3 days)
        skill=50  → rate ≈ 0.683  (full in 4 days)
        skill=1   → rate ≈ 0.602  (full in 5 days)
    """
    skill = max(1, min(100, recovery_skill))
    if skill <= 50:
        t = (skill - 1) / (50 - 1)
        days = _DAYS_AT_SKILL_MIN + t * (_DAYS_AT_SKILL_MID - _DAYS_AT_SKILL_MIN)
    else:
        t = (skill - 50) / (100 - 50)
        days = _DAYS_AT_SKILL_MID + t * (_DAYS_AT_SKILL_MAX - _DAYS_AT_SKILL_MID)
    return 1.0 - (1.0 - _RECOVERY_THRESHOLD) ** (1.0 / days)


def _apply_recovery(energy: float, days: int, recovery_skill: int) -> float:
    """Apply exponential recovery over ``days`` full days."""
    rate = _daily_recovery_rate(recovery_skill)
    for _ in range(days):
        energy += (1.0 - energy) * rate
    return max(0.0, min(1.0, energy))


def availability_weight(state: "PitcherState", game_date: date) -> float:
    if state is None or state.last_game_date is None:
        return 1.0
    days_rest = (game_date - state.last_game_date).days
    last_pitches = state.last_pitch_count or 0

    # Days needed to recover based on pitch count
    if last_pitches >= 60:
        days_needed = 4
    elif last_pitches >= 30:
        days_needed = 3
    elif last_pitches >= 15:
        days_needed = 2
    else:
        days_needed = 1
    if days_rest >= days_needed:
        return 1.0
    return max(0.05, days_rest / days_needed)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PitcherState:
    player_id: str
    current_energy: float
    max_energy: float
    last_game_date: Optional[date] = None
    last_pitch_count: Optional[int] = None
    consecutive_days: int = 0

    @property
    def is_fresh(self) -> bool:
        return self.current_energy >= _RECOVERY_THRESHOLD

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PitcherStateRepository:
    """Repository for managing pitcher energy and rest, scoped to a single league."""

    def __init__(self, conn, league_id: str = ""):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PitcherState]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, current_energy, max_energy, last_game_date,
                   last_pitch_count, consecutive_days
            FROM pitcher_state
            WHERE player_id = %s AND league_id = %s
            """,
            (player_id, self.league_id),
        )
        row = cursor.fetchone()
        if not row:
            return None

        last_game_date = None
        if row["last_game_date"]:
            last_game_date = datetime.fromisoformat(row["last_game_date"]).date()

        return PitcherState(
            player_id=row["player_id"],
            current_energy=row["current_energy"],
            max_energy=row["max_energy"],
            last_game_date=last_game_date,
            last_pitch_count=row["last_pitch_count"],
            consecutive_days=row["consecutive_days"] or 0,
        )

    def get_with_recovery(
        self,
        player_id: str,
        game_date: date,
        recovery_skill: int = 50,
    ) -> PitcherState:
        """
        Get pitcher state with exponential recovery applied up to game_date.

        If pitcher has no history they are returned at full energy (1.0).

        Args:
            player_id:      Player's unique ID.
            game_date:      Date of the upcoming game (from season schedule).
            recovery_skill: Pitcher's recovery skill [1-100].

        Returns:
            PitcherState with current_energy reflecting time elapsed since
            last appearance.
        """
        state = self.get(player_id)

        if not state:
            return PitcherState(player_id=player_id, current_energy=1.0, max_energy=1.0)

        if not state.last_game_date:
            state.current_energy = 1.0
            return state

        days_rest = max(0, (game_date - state.last_game_date).days - 1)
        if days_rest > 0:
            state.consecutive_days = 0
        # Energy: exponential approach toward max_energy (not 1.0)
        # This will never hit with the max set above
        # if days_rest < 0:
        #     logger.warning(
        #         "Data inconsistency for pitcher %s: game_date %s is before "
        #         "last_game_date %s. Returning fresh state.",
        #         player_id,
        #         game_date,
        #         state.last_game_date,
        #     )
        #     return PitcherState(player_id=player_id, current_energy=1.0, max_energy=1.0)

        rate = _daily_recovery_rate(recovery_skill)
        energy = state.current_energy
        for _ in range(days_rest):
            energy += (state.max_energy - energy) * rate
        state.current_energy = max(0.0, min(state.max_energy, energy))
        state.max_energy = min(1.0, state.max_energy + (CAP_REGEN_PER_DAY * days_rest))
        state.current_energy = _apply_recovery(
            state.current_energy, days_rest, recovery_skill
        )
        return state

    # THIS CODE IS NOT USED, BUT MAY BE USEFULE
    # def days_until_ready(
    #     self,
    #     player_id: str,
    #     game_date: date,
    #     recovery_skill: int = 50,
    #     threshold: float = MIN_ENERGY_STARTER,
    # ) -> int:
    #     """
    #     How many more days until this pitcher meets the energy threshold.

    #     Returns 0 if they are already ready.

    #     Args:
    #         player_id:      Player's unique ID.
    #         game_date:      Reference date (usually today in the sim).
    #         recovery_skill: Pitcher's recovery skill [1-100].
    #         threshold:      Minimum energy to be considered ready (default 0.75).
    #     """
    #     state = self.get_with_recovery(player_id, game_date, recovery_skill)
    #     energy = state.current_energy

    #     if energy >= threshold:
    #         return 0

    #     rate = _daily_recovery_rate(recovery_skill)
    #     days = 0
    #     while energy < threshold and days < 365:
    #         energy += (1.0 - energy) * rate
    #         days += 1

    #     return days

    def get_available_pitchers(
        self,
        player_ids: list[str],
        game_date: date,
        recovery_skills: dict[str, int] | None = None,
        min_energy: float = MIN_ENERGY_STARTER,
    ) -> list[PitcherState]:
        """
        Return pitchers whose current energy meets the minimum threshold.

        Args:
            player_ids:      Pitcher IDs to check.
            game_date:       Date of the upcoming game.
            recovery_skills: Optional mapping of player_id → recovery skill.
                             Defaults to 50 for any pitcher not in the map.
            min_energy:      Minimum energy to be considered available.

        Returns:
            List of PitcherStates (with recovery applied) for available pitchers.
        """
        recovery_skills = recovery_skills or {}
        available = []
        for player_id in player_ids:
            skill = recovery_skills.get(player_id, 50)
            state = self.get_with_recovery(player_id, game_date, skill)
            if state.current_energy >= min_energy:
                available.append(state)
        return available

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_pitcher_state(self, state: PitcherState) -> None:
        """
        Upsert a pitcher state row.

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
            INSERT INTO pitcher_state
                (player_id, league_id, current_energy, max_energy,
                 last_game_date, last_pitch_count, consecutive_days)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(player_id, league_id) DO UPDATE SET
                current_energy   = excluded.current_energy,
                max_energy       = excluded.max_energy,
                last_game_date   = excluded.last_game_date,
                last_pitch_count = excluded.last_pitch_count,
                consecutive_days = excluded.consecutive_days
            """,
            (
                state.player_id,
                self.league_id,
                energy,
                max(0.0, min(1.0, round(state.max_energy, 4))),
                last_game_date_str,
                state.last_pitch_count,
                state.consecutive_days,
            ),
        )
        self.conn.commit()

    def update_after_game(
        self,
        player_id: str,
        final_energy: float,
        max_energy: float,
        pitch_count: int,
        game_date: date,
    ) -> None:
        """
        Persist pitcher state after a game appearance.

        Pass fatigue.energy and fatigue.pitches_thrown directly from
        the PitcherFatigue instance that ran the game.

        No-ops if pitch_count is 0 — this protects pitchers who warmed up
        or were rostered but never appeared from having their last_game_date
        incorrectly updated.

        Args:
            player_id:    Player's unique ID.
            final_energy: fatigue.energy at end of game.
            pitch_count:  fatigue.pitches_thrown for the game.
            game_date:    Date the game was played.
        """
        if pitch_count == 0:
            return

        existing = self.get(player_id)
        if existing and existing.last_game_date:
            days_rest = (game_date - existing.last_game_date).days
            consecutive_days = existing.consecutive_days + 1 if days_rest == 1 else 1
        else:
            consecutive_days = 1

        self.save_pitcher_state(
            PitcherState(
                player_id=player_id,
                current_energy=final_energy,
                max_energy=max_energy,
                last_game_date=game_date,
                last_pitch_count=pitch_count,
                consecutive_days=consecutive_days,
            )
        )

    def delete(self, player_id: str) -> bool:
        """
        Delete a pitcher's state row. Returns True if a row was removed.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM pitcher_state WHERE player_id = %s AND league_id = %s",
            (player_id, self.league_id),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted

    def clear_all_pitcher_state(self) -> int:
        """Delete all pitcher state rows. Call between seasons. Returns row count deleted."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM pitcher_state WHERE league_id = %s",
            (self.league_id,),
        )
        deleted = cursor.rowcount
        # self.conn.commit()
        return deleted
