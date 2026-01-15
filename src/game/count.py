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

    def __init__(self):
        """Initialize balls and strikes to 0."""
        self.balls = 0
        self.strikes = 0

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
        return CountSnapshot(
            balls=self.balls,
            strikes=self.strikes,
        )

    # ---------- Mutations ----------

    def add_ball(self):
        if self.balls < 4:
            self.balls += 1

    def add_strike(self):
        if self.strikes < 3:
            self.strikes += 1

    def reset(self):
        self.balls = 0
        self.strikes = 0
