# src/game/inning.py
class Inning(object):
    """Keep track of inning related information."""

    def __init__(self):
        """Set up a new inning. Start in the top of the 1st with no outs."""
        self._number = 1
        self._outs = 0
        self.top = True

    # ---------- number property ----------

    @property
    def number(self) -> int:
        """Get the current inning number."""
        return self._number

    @number.setter
    def number(self, value: int) -> None:
        """Set the inning number with validation."""
        if not isinstance(value, int):
            raise TypeError(
                f"Inning number must be an integer, got {type(value).__name__}"
            )
        if value < 1:
            raise ValueError(f"Inning number must be at least 1, got {value}")
        self._number = value

    # ---------- outs property ----------

    @property
    def outs(self) -> int:
        """Get the current out count."""
        return self._outs

    @outs.setter
    def outs(self, value: int) -> None:
        """Set the out count with validation."""
        if not isinstance(value, int):
            raise TypeError(f"Outs must be an integer, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"Outs cannot be negative, got {value}")
        if value > 3:
            raise ValueError(f"Outs cannot exceed 3, got {value}")
        self._outs = value

    # ---------- computed properties ----------

    @property
    def bottom(self) -> bool:
        """True if in the bottom half of the inning."""
        return not self.top

    @property
    def is_over(self) -> bool:
        """True if this half-inning is over (3 outs)."""
        return self._outs >= 3

    # ---------- string representation ----------

    def __str__(self) -> str:
        """Return an inning string."""
        if self.top:
            return f"Top of {self._number}"
        else:
            return f"Bottom of {self._number}"

    # ---------- mutations ----------

    def increment(self) -> None:
        """Move to the next half inning."""
        if self.top:
            self.top = False
        else:
            self.top = True
            self._number += 1  # Direct access to bypass validation
        self.reset_outs()

    def record_out(self, n: int = 1) -> None:
        """
        Record n outs.

        Args:
            n: Number of outs to record (default 1)

        Raises:
            ValueError: If n is negative or would exceed 3 total outs
        """
        if n < 0:
            raise ValueError(f"Cannot record negative outs: {n}")
        if self._outs + n > 3:
            raise ValueError(
                f"Cannot exceed 3 outs (currently {self._outs}, trying to add {n})"
            )
        self._outs += n

    def reset_outs(self) -> None:
        """Set the outs to zero."""
        self._outs = 0


# # src/game/inning.py
# from dataclasses import dataclass

# @dataclass(frozen=True)
# class InningSnapshot:
#     number: int
#     top: bool
#     outs: int


# class Inning(object):
#     """Keep track of inning related information."""

#     def __init__(self):
#         """Set up a new inning.  Start in the top of the 1st with no outs."""
#         self.number = 1
#         self.top = True
#         self.outs = 0

#     @property
#     def bottom(self):
#         return not self.top

#     @property
#     def is_over(self) -> bool:
#         """True if this half-inning is over (3 outs)."""
#         return self.outs >= 3

#     def __str__(self):
#         """Return an inning string."""
#         if self.top:
#             return f"Top of {self.number}"
#         else:
#             return f"Bottom of {self.number}"

#     def increment(self) -> None:
#         """Move to the next half inning."""
#         if self.top:
#             self.top = False
#         else:
#             self.top = True
#             self.number += 1
#         self.reset_outs()

#     def record_out(self, n: int = 1) -> None:
#         if n < 0:
#             raise ValueError(f"Cannot record negative outs: {n}")
#         if self.outs + n > 3:
#             raise ValueError(f"Cannot exceed 3 outs (currently {self.outs}, trying to add {n})")
#         self.outs += n

#     def reset_outs(self) -> None:
#         """Set the outs to zero."""
#         self.outs = 0

#     def snapshot(self) -> InningSnapshot:
#         return InningSnapshot(number=self.number, top=self.top, outs=self.outs)
