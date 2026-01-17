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

# Public API
FIRST = 1
SECOND = 2
THIRD = 3
HOME = 4
VALID_BASES = (FIRST, SECOND, THIRD)
VALID_DESTINATIONS = (FIRST, SECOND, THIRD, HOME)


@dataclass(frozen=True)
class BasesSnapshot:
    first: Optional[str] = None
    second: Optional[str] = None
    third: Optional[str] = None


class Bases:
    """
    Tracks base occupancy.

    Internal representation:
        base_number (1-3) -> runner_id
    """

    def __init__(self):
        self._bases: Dict[int, str] = {}

    def __str__(self):
        parts = []
        for base in (THIRD, SECOND, FIRST):
            if base in self._bases:
                parts.append(f"{base}B={self._bases[base]}")
        return "Bases: " + (" ".join(parts) if parts else "Empty")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def runner_on(self, base: int) -> Optional[str]:
        if base not in VALID_BASES:
            raise ValueError(f"Invalid base: {base}")
        return self._bases.get(base)

    def base_of(self, runner_id: str) -> Optional[int]:
        found = [b for b, r in self._bases.items() if r == runner_id]
        if len(found) > 1:
            raise RuntimeError(f"Runner {runner_id} on multiple bases: {found}")
        return found[0] if found else None

    def occupied_map(self) -> dict[int, str]:
        """
        Returns a snapshot of occupied bases.

        Keys are base numbers (1, 2, 3),
        values are runner_ids.

        Used by pure rule helpers (no mutation).
        """
        occupied = {}

        for base in (1, 2, 3):
            runner = self.runner_on(base)
            if runner is not None:
                occupied[base] = runner

        return occupied

    def runners(self) -> list[str]:
        """Return list of all runner IDs currently on base."""
        return list(self._bases.values())

    def has_runner(self, runner_id: str) -> bool:
        """Check if a specific runner is on any base."""
        return runner_id in self._bases.values()

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
        if to_base not in VALID_DESTINATIONS:
            raise ValueError(f"Invalid to_base: {to_base}")

        # --- Validate origin ---
        if from_base is None:
            if self.base_of(runner_id) is not None:
                raise RuntimeError(f"Runner {runner_id} already on base")
        else:
            if from_base not in VALID_BASES:
                raise ValueError(f"Invalid from_base: {from_base}")
            if self._bases.get(from_base) != runner_id:
                raise RuntimeError(f"Runner {runner_id} not on base {from_base}")
            del self._bases[from_base]

        # --- Handle scoring ---
        if to_base == HOME:
            return

        # --- Destination must be empty ---
        if to_base in self._bases:
            raise RuntimeError(
                f"Base {to_base} already occupied by {self._bases[to_base]}. "
                f"Cannot advance {runner_id}. Current state: {self}"
            )
            # raise RuntimeError(
            #     f"Base {to_base} already occupied by {self._bases[to_base]}"
            # )

        self._bases[to_base] = runner_id
        # self._assert_consistent() # Use in debug mode

    def remove(
        self,
        runner_id: str,
        from_base: int,
    ):
        """
        Remove a runner from the bases (out, caught stealing, etc.).
        """

        if from_base not in VALID_BASES:
            raise ValueError(f"Invalid from_base: {from_base}")

        if self._bases.get(from_base) != runner_id:
            raise RuntimeError(f"Runner {runner_id} not on base {from_base}")

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


# from __future__ import annotations

# from typing import Dict, Optional

# # Public API
# FIRST = 1
# SECOND = 2
# THIRD = 3

# class Bases:
#     """
#     Tracks base occupancy.

#     Internal representation:
#         base_number (1-3) -> runner_id
#     """

#     def __init__(self):
#         self._bases: Dict[int, str] = {}

#     def __str__(self):
#         output = "Bases: "
#         try:
#             output += f"3rd = {self._bases[3]} "
#         except:
#             pass
#         try:
#             output += f"2nd = {self._bases[2]} "
#         except:
#             pass
#         try:
#             output += f"1st = {self._bases[1]} "
#         except:
#             pass
#         if output == "Bases: ":
#             output += "Empty"
#         return output

#     # ------------------------------------------------------------------
#     # Queries
#     # ------------------------------------------------------------------

#     def runner_on(self, base: int) -> Optional[str]:
#         return self._bases.get(base)

#     def base_of(self, runner_id: str) -> Optional[int]:
#         for base, runner in self._bases.items():
#             if runner == runner_id:
#                 return base
#         return None

#     def occupied_bases(self) -> Dict[int, str]:
#         return dict(self._bases)

#     # ------------------------------------------------------------------
#     # Mutations (event-driven)
#     # ------------------------------------------------------------------

#     def advance(
#         self,
#         runner_id: str,
#         from_base: Optional[int],
#         to_base: int,
#     ):
#         """
#         Advance a runner from one base to another.

#         from_base:
#             None → batter entering bases
#         to_base:
#             1-3: occupy base
#             4: score (remove runner)
#         """

#         # --- Validate destination ---
#         if to_base not in (1, 2, 3, 4):
#             raise ValueError(f"Invalid base: {to_base}")

#         # --- Validate origin ---
#         if from_base is None:
#             # Batter entering bases
#             if self.base_of(runner_id) is not None:
#                 raise RuntimeError(f"Runner {runner_id} already on base")
#         else:
#             if self._bases.get(from_base) != runner_id:
#                 raise RuntimeError(f"Runner {runner_id} not on base {from_base}")
#             del self._bases[from_base]

#         # --- Handle scoring ---
#         if to_base == 4:
#             # Runner scores → not stored on bases
#             return

#         # --- Destination must be empty ---
#         if to_base in self._bases:
#             raise RuntimeError(
#                 f"Base {to_base} already occupied by {self._bases[to_base]}"
#             )

#         self._bases[to_base] = runner_id

#     def remove(
#         self,
#         runner_id: str,
#         from_base: Optional[int],
#     ):
#         """
#         Remove a runner from the bases (out, caught stealing, etc.).
#         """

#         if from_base is None:
#             raise RuntimeError(f"Cannot remove runner {runner_id} without base")

#         if self._bases.get(from_base) != runner_id:
#             raise RuntimeError(f"Runner {runner_id} not on base {from_base}")

#         del self._bases[from_base]

#     # ------------------------------------------------------------------
#     # Reset
#     # ------------------------------------------------------------------

#     def clear(self):
#         """Clear all bases (inning end)."""
#         self._bases.clear()
