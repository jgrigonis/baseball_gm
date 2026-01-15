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

from typing import Dict, Optional


class Bases:
    """
    Tracks base occupancy.

    Internal representation:
        base_number (1-3) -> runner_id
    """

    def __init__(self):
        self._bases: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def runner_on(self, base: int) -> Optional[str]:
        return self._bases.get(base)

    def base_of(self, runner_id: str) -> Optional[int]:
        for base, runner in self._bases.items():
            if runner == runner_id:
                return base
        return None

    def occupied_bases(self) -> Dict[int, str]:
        return dict(self._bases)

    # ------------------------------------------------------------------
    # Mutations (event-driven)
    # ------------------------------------------------------------------

    def advance(
        self,
        runner_id: str,
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
        if to_base not in (1, 2, 3, 4):
            raise ValueError(f"Invalid base: {to_base}")

        # --- Validate origin ---
        if from_base is None:
            # Batter entering bases
            if self.base_of(runner_id) is not None:
                raise RuntimeError(f"Runner {runner_id} already on base")
        else:
            if self._bases.get(from_base) != runner_id:
                raise RuntimeError(f"Runner {runner_id} not on base {from_base}")
            del self._bases[from_base]

        # --- Handle scoring ---
        if to_base == 4:
            # Runner scores → not stored on bases
            return

        # --- Destination must be empty ---
        if to_base in self._bases:
            raise RuntimeError(
                f"Base {to_base} already occupied by {self._bases[to_base]}"
            )

        self._bases[to_base] = runner_id

    def remove(
        self,
        runner_id: str,
        from_base: Optional[int],
    ):
        """
        Remove a runner from the bases (out, caught stealing, etc.).
        """

        if from_base is None:
            raise RuntimeError(f"Cannot remove runner {runner_id} without base")

        if self._bases.get(from_base) != runner_id:
            raise RuntimeError(f"Runner {runner_id} not on base {from_base}")

        del self._bases[from_base]

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def clear(self):
        """Clear all bases (inning end)."""
        self._bases.clear()
