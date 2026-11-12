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

"""

from __future__ import annotations

import logging
from datetime import datetime, date
from collections.abc import Iterable
from dataclasses import dataclass, replace

from src.util.clamp import clamp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recovery calibration
# ---------------------------------------------------------------------------

MIN_ENERGY_STARTER = 0.83

# Cap: slow passive regeneration
CAP_REGEN_PER_DAY = 0.0045


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _daily_recovery_rate(recovery_skill: int) -> float:
    """
    Actual energy recovered as a number.

    At recovery skill 100 a pitcher can recover 0 to 100 in 4 days rest
    At recovery skill 60 a pitcher can recover 0 to 100 in 7 days rest
    At recovery skill 1 a pitcher can recover 0 to 100 in 12 days rest

    Recovery is linear.

    """
    skill = max(1, min(100, recovery_skill))
    return (1 / 800) * skill + 1 / 16


def _apply_recovery(
    energy: float, days: int, recovery_skill: int, rate_mult: float = 1.0
) -> float:
    """Apply linear recovery over ``days`` full days."""
    rate = _daily_recovery_rate(recovery_skill) * rate_mult
    for _ in range(days):
        energy += rate
    return max(0.0, min(1.0, energy))


def availability_weight(state: PitcherState, game_date: date) -> float:
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
    last_game_date: date | None = None
    last_pitch_count: int | None = None
    consecutive_days: int = 0


def recover_pitcher_state(
    state: PitcherState | None,
    player_id: str,
    game_date: date,
    recovery_skill: int = 50,
    rate_mult: float = 1.0,
) -> PitcherState:
    """
    Return a copy of a stored pitcher state with recovery applied up to game_date.

    ``state`` is the raw row as returned by ``PitcherStateRepository.get`` or
    ``get_many`` (None when the pitcher has no history). It is not modified,
    so one set of raw states can be reused for several recovery calculations.
    ``rate_mult`` speeds or slows the daily recovery: his team's Facilities
    (src/league/budget.py facilities_recovery).
    """
    if not state:
        return PitcherState(player_id=player_id, current_energy=1.0, max_energy=1.0)

    state = replace(state)
    if not state.last_game_date:
        state.current_energy = 1.0
        return state

    days_rest = max(0, (game_date - state.last_game_date).days - 1)
    if days_rest > 0:
        state.consecutive_days = 0

    rate = min(0.95, _daily_recovery_rate(recovery_skill) * rate_mult)
    energy = state.current_energy
    for _ in range(days_rest):
        energy += (state.max_energy - energy) * rate
    state.current_energy = max(0.0, min(state.max_energy, energy))
    cap_regen = CAP_REGEN_PER_DAY * recovery_skill / 50
    state.max_energy = min(1.0, state.max_energy + (cap_regen * days_rest))
    state.current_energy = _apply_recovery(
        state.current_energy, days_rest, recovery_skill, rate_mult
    )
    return state


def _row_to_state(row) -> PitcherState:
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


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PitcherStateRepository:
    """Repository for managing pitcher energy and rest, scoped to a single league."""

    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> PitcherState | None:
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
        return _row_to_state(row)

    def get_many(self, player_ids: Iterable[str]) -> dict[str, PitcherState]:
        """
        Fetch stored states for many pitchers in one query.

        Returns a dict keyed by player_id. Pitchers with no stored state are
        left out.
        """
        player_ids = list(player_ids)
        if not player_ids:
            return {}
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT player_id, current_energy, max_energy, last_game_date,
                   last_pitch_count, consecutive_days
            FROM pitcher_state
            WHERE player_id = ANY(%s) AND league_id = %s
            """,
            (player_ids, self.league_id),
        )
        return {row["player_id"]: _row_to_state(row) for row in cursor.fetchall()}

    def get_with_recovery(
        self,
        player_id: str,
        game_date: date,
        recovery_skill: int = 50,
        rate_mult: float = 1.0,
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
        return recover_pitcher_state(
            self.get(player_id), player_id, game_date, recovery_skill, rate_mult
        )

    # THIS CODE IS NOT USED, BUT MAY BE USEFUL
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
        self.save_many([state])

    def save_many(self, states: Iterable[PitcherState]) -> None:
        """Upsert many pitcher state rows in one batch (see save_pitcher_state)."""
        params = [self._save_params(state) for state in states]
        if not params:
            return
        cursor = self.conn.cursor()
        cursor.executemany(
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
            params,
        )

    def _save_params(self, state: PitcherState) -> tuple:
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
            max(0.0, min(1.0, round(state.max_energy, 4))),
            last_game_date_str,
            state.last_pitch_count,
            state.consecutive_days,
        )

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
        self.update_many_after_game(
            [(player_id, final_energy, max_energy, pitch_count)], game_date
        )

    def update_many_after_game(
        self,
        appearances: Iterable[tuple[str, float, float, int]],
        game_date: date,
    ) -> None:
        """
        Batch version of update_after_game: one read and one write for the
        whole game instead of two queries per pitcher.

        Args:
            appearances: (player_id, final_energy, max_energy, pitch_count)
                         for each pitcher. Entries with a pitch_count of 0
                         are skipped, as in update_after_game.
            game_date:   Date the game was played.
        """
        appearances = [a for a in appearances if a[3] != 0]
        if not appearances:
            return

        existing_states = self.get_many(a[0] for a in appearances)
        new_states = []
        for player_id, final_energy, max_energy, pitch_count in appearances:
            existing = existing_states.get(player_id)
            if existing and existing.last_game_date:
                days_rest = (game_date - existing.last_game_date).days
                consecutive_days = (
                    existing.consecutive_days + 1 if days_rest == 1 else 1
                )
            else:
                consecutive_days = 1

            new_states.append(
                PitcherState(
                    player_id=player_id,
                    current_energy=final_energy,
                    max_energy=max_energy,
                    last_game_date=game_date,
                    last_pitch_count=pitch_count,
                    consecutive_days=consecutive_days,
                )
            )
        self.save_many(new_states)

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
        return deleted
