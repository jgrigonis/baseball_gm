# src/game/count.py
"""
The Count class.  Keep track of balls and strikes.
✅ Track balls & strikes
✅ Allow controlled increments
✅ Know when it is full (3-2, 3 balls, 2 strikes)
❌ NOT reset itself
❌ NOT create outs, walks, or strikeouts

"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CountSnapshot:
    balls: int
    strikes: int


class Count:
    """
    Tracks balls and strikes for the current plate appearance.
    No game logic. No automatic resets.
    """

    def __init__(self, balls=0, strikes=0):
        """Initialize balls and strikes to 0."""
        self.balls = balls
        self.strikes = strikes

    def __str__(self):
        return f"{self.balls}-{self.strikes}"

    # ---------- Queries ----------

    @property
    def is_full_count(self) -> bool:
        return self.balls == 3 and self.strikes == 2

    @property
    def is_three_balls(self) -> bool:
        return self.balls == 3

    @property
    def is_two_strikes(self) -> bool:
        return self.strikes == 2

    def snapshot(self) -> CountSnapshot:
        """Snapshot the count."""
        return CountSnapshot(
            balls=self.balls,
            strikes=self.strikes,
        )

    # ---------- Mutations ----------

    def add_ball(self) -> None:
        """Add ball to count."""
        if self.balls >= 4:
            raise ValueError(f"Cannot add ball: already at {self.balls} balls")
        self.balls += 1

    def add_strike(self) -> None:
        """Add strike to count."""
        if self.strikes >= 3:
            raise ValueError(f"Cannot add strike: already at {self.strikes} strikes")
        self.strikes += 1

    def reset(self) -> None:
        """Reset the count."""
        self.balls = 0
        self.strikes = 0
