# src/stats/fielding_stats.py
from dataclasses import dataclass


@dataclass
class FieldingStats:
    """The fielding statistics object."""

    # General fielding
    putouts: int = 0
    assists: int = 0
    errors: int = 0
    chances: int = 0  # putouts + assists + errors

    # Catcher-specific
    passed_balls: int = 0
    catcher_interferences: int = 0
    catcher_cs: int = 0  # Caught stealing
    catcher_sb: int = 0  # Stolen bases allowed

    def __str__(self):
        """Return the string representation of the fielding statistics."""
        return (
            "Fielding Stats:\n"
            f"  PO: {self.putouts}\n"
            f"  A: {self.assists}\n"
            f"  E: {self.errors}\n"
            f"  TC: {self.chances}\n"
            f"  FPCT: {self.fielding_percentage:.3f}"
        )

    @property
    def fielding_percentage(self):
        """Return the fielding percentage."""
        if self.chances == 0:
            return 1.0
        return (self.putouts + self.assists) / self.chances

    def add(self, other):
        """Used for aggregating stats, or adding an entire stat instance to another."""
        for attr in vars(self):
            # Skip non-numeric attributes
            if attr.startswith("_"):
                continue
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    def putout(self):
        """Add a putout."""
        self.putouts += 1
        self.chances += 1

    def assist(self):
        """Add an assist."""
        self.assists += 1
        self.chances += 1

    def error(self):
        """Add an error."""
        self.errors += 1
        self.chances += 1

    def passed_ball(self):
        """Add a passed ball."""
        self.passed_balls += 1
        self.chances += 1

    def catcher_interference(self):
        """Add a catcher interference."""
        self.catcher_interferences += 1
        self.error()

    def catcher_caught_stealing(self):
        """Add a catcher caught stealing."""
        self.catcher_cs += 1

    def catcher_stolen_base(self):
        """Add a catcher stolen base."""
        self.catcher_sb += 1
