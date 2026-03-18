# src/db/repositories/injury_repo.py
"""
src/db/repositories/injury_repo.py

Repository for player injury tracking.

Tracks how many games a player must miss due to injury. The injury
system works as follows:

- When a player is injured during a game, a row is inserted with
  games_remaining set based on injury severity.
- At the START of each game, before lineups are set, tick_all() is
  called to decrement games_remaining for all injured players on
  both rosters.
- When games_remaining reaches 0 the row is deleted and the player's
  is_injured flag is cleared.
- Lineup builders call is_injured() before rostering any player.

Injury duration table (games missed, not counting the game of injury):
    minor strain / bruise:   3-7
    muscle pull:            10-20
    ligament / sprain:      15-30
    fracture:               30-50
    serious (e.g. ACL):     50-80
"""

from __future__ import annotations

import random
import logging
from dataclasses import dataclass
from typing import Optional

from src.db.repositories.player_energy import PlayerEnergyRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injury severity tiers
# ---------------------------------------------------------------------------

INJURY_TIERS = {
    "minor": (1, 7),  # Day to Day
    "moderate": (7, 50),  # 10 Day IL
    "pitcher": (12, 50),  # 15 Day IL (for pitchers)
    "severe": (57, 90),  # 60 day IL
    "surgery": (270, 540),  # surgery
}


def roll_games_missed(severity: str, rng: random.Random | None = None) -> int:
    """
    Roll a random games-missed count for the given severity tier.

    Args:
        severity: One of the INJURY_TIERS keys.
        rng:      Optional seeded RNG. Uses random module if not provided.

    Returns:
        Integer number of games the player will miss.
    """
    lo, hi = INJURY_TIERS.get(severity, INJURY_TIERS["minor"])
    if rng:
        return rng.randint(lo, hi)
    return random.randint(lo, hi)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class PlayerInjury:
    """Current injury state for a player."""

    player_id: str
    games_remaining: int

    @property
    def is_active(self) -> bool:
        return self.games_remaining > 0


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class InjuryRepository:
    """Repository for managing player injuries."""

    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PlayerInjury]:
        """Return the injury record for a player, or None if not injured."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT player_id, games_remaining FROM player_injuries WHERE player_id = ?",
            (player_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return PlayerInjury(player_id=row[0], games_remaining=row[1])

    def is_injured(self, player_id: str) -> bool:
        """Return True if the player has an active injury."""
        injury = self.get(player_id)
        return injury is not None and injury.is_active

    def get_all_injured(self) -> list[PlayerInjury]:
        """Return all currently injured players."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT player_id, games_remaining FROM player_injuries WHERE games_remaining > 0"
        )
        return [
            PlayerInjury(player_id=row[0], games_remaining=row[1])
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def injure(
        self,
        player_id: str,
        severity: str = "minor",
        rng: random.Random | None = None,
        games: int | None = None,
    ) -> PlayerInjury:
        """
        Record a new injury for a player.

        If the player is already injured, only updates if the new injury
        is longer than the remaining games (worse injury wins).

        Args:
            player_id: Player's unique ID.
            severity:  Tier name from INJURY_TIERS. Ignored if games is set.
            rng:       Optional seeded RNG for duration roll.
            games:     Explicit games-missed count. Overrides severity roll.

        Returns:
            The resulting PlayerInjury.
        """
        games_missed = games if games is not None else roll_games_missed(severity, rng)

        existing = self.get(player_id)
        if existing and existing.games_remaining >= games_missed:
            logger.debug(
                "Player %s already has %d games remaining — new injury (%d) ignored.",
                player_id,
                existing.games_remaining,
                games_missed,
            )
            return existing

        injury = PlayerInjury(player_id=player_id, games_remaining=games_missed)
        self._save(injury)

        # Keep the season injury counter in sync
        energy_repo = PlayerEnergyRepository(self.conn)
        state = energy_repo.get(player_id)
        if state:
            state.injuries_this_season += 1
            energy_repo.save(state)

        logger.info(
            "Player %s injured: %s (%d games).", player_id, severity, games_missed
        )
        return injury

    def tick(self, player_id: str) -> Optional[PlayerInjury]:
        """
        Decrement games_remaining by 1 for a single player.

        Deletes the row and returns None when the player is healed.
        Returns the updated injury if still active.

        Call this at the START of each game before lineup construction.
        """
        injury = self.get(player_id)
        if not injury:
            return None

        injury.games_remaining -= 1

        if injury.games_remaining <= 0:
            self.clear(player_id)
            logger.info("Player %s injury cleared — available to play.", player_id)
            return None

        self._save(injury)
        return injury

    def tick_all(self, player_ids: list[str]) -> dict[str, Optional[PlayerInjury]]:
        """
        Tick injuries for a list of players (both rosters before each game).

        Returns a dict of player_id → PlayerInjury (or None if just healed).
        Only includes players who had an active injury at call time.
        """
        results = {}
        for player_id in player_ids:
            if self.is_injured(player_id):
                results[player_id] = self.tick(player_id)
        return results

    def clear(self, player_id: str) -> bool:
        """
        Remove a player's injury record entirely.

        Returns True if a row was deleted.
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM player_injuries WHERE player_id = ?", (player_id,))
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted

    def clear_all(self) -> int:
        """Delete all injury rows. Call between seasons. Returns row count deleted."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM player_injuries")
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self, injury: PlayerInjury) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO player_injuries (player_id, games_remaining)
            VALUES (?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                games_remaining = excluded.games_remaining
            """,
            (injury.player_id, injury.games_remaining),
        )
        self.conn.commit()
