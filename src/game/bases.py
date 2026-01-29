# src/game/bases.py
"""

Has no baseball rules
Enforces hard correctness invariants
Is safe against race-condition bugs
Is fully reconstructible from events

These must never be violated:
A runner may occupy at most one base
A base (1-3) may contain at most one runner
You cannot advance a runner that does not exist
You cannot remove a runner that does not exist
Home plate (base 4) is not a stored base

Bases DOES:
Track which runner is on which base
Enforce physical constraints (one runner per base)
Allow explicit advances and removals

Bases DOES NOT:
Decide outcomes (safe/out)
Know why runners move
Handle scoring logic (that's ScoreEvent)

Events describe reality.
Bases enforces physics.
Resolver enforces baseball.

"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

from src.player.player_in_game import PlayerInGame

# Public API
FIRST = 1
SECOND = 2
THIRD = 3
HOME = 4
VALID_BASES = (FIRST, SECOND, THIRD)
VALID_DESTINATIONS = (FIRST, SECOND, THIRD, HOME)


@dataclass(frozen=True)
class BasesSnapshot:
    first: Optional[PlayerInGame] = None
    second: Optional[PlayerInGame] = None
    third: Optional[PlayerInGame] = None


class Bases:
    """
    Tracks base occupancy.

    Internal representation:
        base_number (1-3) -> runner
    """

    def __init__(self):
        self._bases: Dict[int, PlayerInGame] = {}

    def __str__(self):
        """
        Outputs the bases as a human-readable string.

        Examples:
        - "Bases empty"
        - "Man on first"
        - "Men on first and second"
        - "Bases loaded"
        """
        occupied = []
        if FIRST in self._bases:
            occupied.append("first")
        if SECOND in self._bases:
            occupied.append("second")
        if THIRD in self._bases:
            occupied.append("third")

        if not occupied:
            return "Bases empty"

        if len(occupied) == 3:
            return "Bases loaded"

        # Use "Man" for single runner, "Men" for multiple
        prefix = "Man" if len(occupied) == 1 else "Men"

        # Format the base list nicely
        if len(occupied) == 1:
            bases_str = occupied[0]
        elif len(occupied) == 2:
            bases_str = f"{occupied[0]} and {occupied[1]}"
        else:
            # This shouldn't happen since 3 is handled above, but just in case
            bases_str = ", ".join(occupied[:-1]) + f" and {occupied[-1]}"

        return f"{prefix} on {bases_str}"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def runner_on(self, base: int) -> Optional[PlayerInGame]:
        if base not in VALID_BASES:
            raise ValueError(f"Invalid base: {base}")
        return self._bases.get(base)

    def base_of(self, runner: PlayerInGame) -> Optional[int]:
        found = [b for b, r in self._bases.items() if r == runner]
        if len(found) > 1:
            raise RuntimeError(f"Runner {runner.name} on multiple bases: {found}")
        return found[0] if found else None

    def occupied_map(self) -> dict[int, PlayerInGame]:
        """
        Returns a snapshot of occupied bases.

        Keys are base numbers (1, 2, 3),
        values are runners.

        Used by pure rule helpers (no mutation).
        """
        occupied = {}

        for base in (FIRST, SECOND, THIRD):
            runner = self.runner_on(base)
            if runner is not None:
                occupied[base] = runner

        return occupied

    def runners(self) -> list[PlayerInGame]:
        """Return list of all runners currently on base."""
        return list(self._bases.values())

    def has_runner(self, runner: PlayerInGame) -> bool:
        """Check if a specific runner is on any base."""
        return runner in self._bases.values()

    @property
    def is_empty(self) -> bool:
        """True if no runners on base."""
        return len(self._bases) == 0

    @property
    def is_loaded(self) -> bool:
        """True if bases are loaded."""
        return len(self._bases) == 3

    # ------------------------------------------------------------------
    # Mutations (event-driven)
    # ------------------------------------------------------------------

    def advance(
        self,
        runner: PlayerInGame,
        from_base: Optional[int],
        to_base: int,
    ):
        """
        Advance a runner from one base to another.

        from_base:
            None → batter entering bases
        to_base:
            1-3: occupy base
            4: score (remove runner)
        """

        # --- Validate destination ---
        if to_base not in VALID_DESTINATIONS:
            raise ValueError(f"Invalid to_base: {to_base}")

        # --- Validate origin ---
        if from_base is None:
            if self.base_of(runner) is not None:
                raise RuntimeError(f"Runner {runner.name} already on base")
        else:
            if from_base not in VALID_BASES:
                raise ValueError(f"Invalid from_base: {from_base}")
            if self._bases.get(from_base) != runner:
                raise RuntimeError(f"Runner {runner.name} not on base {from_base}")
            del self._bases[from_base]

        # --- Handle scoring ---
        if to_base == HOME:
            return

        # --- Destination must be empty ---
        if to_base in self._bases:
            raise RuntimeError(
                f"Base {to_base} already occupied by {self._bases[to_base]}. "
                f"Cannot advance {runner.name}. Current state: {self}"
            )

        self._bases[to_base] = runner
        # self._assert_consistent() # Use in debug mode

    def remove(
        self,
        runner: PlayerInGame,
        from_base: int,
    ):
        """
        Remove a runner from the bases (out, caught stealing, etc.).
        """

        if from_base not in VALID_BASES:
            raise ValueError(f"Invalid from_base: {from_base}")

        if self._bases.get(from_base) != runner:
            raise RuntimeError(f"Runner {runner.name} not on base {from_base}")

        del self._bases[from_base]

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def clear(self):
        """Clear all bases (inning end)."""
        self._bases.clear()

    # ------------------------------------------------------------------
    # Snapshotting
    # ------------------------------------------------------------------
    def snapshot(self) -> BasesSnapshot:
        return BasesSnapshot(
            first=self.runner_on(FIRST),
            second=self.runner_on(SECOND),
            third=self.runner_on(THIRD),
        )

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------
    def _assert_consistent(self):
        if len(set(self._bases.values())) != len(self._bases):
            raise RuntimeError("Runner appears on multiple bases")

    # ------------------------------------------------------------------
    # Testing
    # ------------------------------------------------------------------
    def place_runner(self, base: int, runner: PlayerInGame):
        if base not in VALID_BASES:
            raise ValueError(f"Invalid base: {base}")
        self._bases[base] = runner
