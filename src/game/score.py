# src/game/score.py
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScoreSnapshot:
    """Immutable snapshot of the current score state."""

    away_innings: tuple[int, ...]
    home_innings: tuple[int, ...]
    away_total: int
    home_total: int


class Score:
    """
    Track runs scored by inning for both teams.

    Responsibilities:
    ✅ Track runs per inning for home and away teams
    ✅ Calculate total runs for each team
    ✅ Ensure innings exist before scoring
    ✅ Validate inning numbers

    Does NOT:
    ❌ Decide game outcomes
    ❌ Know about outs or game rules
    ❌ Track current inning
    """

    def __init__(self):
        """Initialize with no runs scored."""
        self._away_innings: list[int] = []
        self._home_innings: list[int] = []

    # ---------- Properties ----------

    @property
    def away(self) -> int:
        """Total runs scored by away team."""
        return sum(self._away_innings)

    @property
    def home(self) -> int:
        """Total runs scored by home team."""
        return sum(self._home_innings)

    @property
    def away_innings(self) -> list[int]:
        """Read-only access to away innings (returns copy)."""
        return list(self._away_innings)

    @property
    def home_innings(self) -> list[int]:
        """Read-only access to home innings (returns copy)."""
        return list(self._home_innings)

    @property
    def differential(self) -> int:
        """Run differential (home - away). Positive means home is winning."""
        return self.home - self.away

    @property
    def leader(self) -> Literal["home", "away", "tied"]:
        """Which team is leading."""
        if self.home > self.away:
            return "home"
        elif self.away > self.home:
            return "away"
        return "tied"

    @property
    def is_tied(self) -> bool:
        """True if the score is tied."""
        return self.home == self.away

    # ---------- Queries ----------

    def runs_in_inning(self, inning_number: int, *, top: bool) -> int:
        """
        Get runs scored in a specific inning.

        Args:
            inning_number: The inning number (1-indexed)
            top: True for away (top half), False for home (bottom half)

        Returns:
            Number of runs scored, or 0 if inning hasn't been played yet
        """
        self._validate_inning_number(inning_number)

        innings = self._away_innings if top else self._home_innings

        if inning_number > len(innings):
            return 0
        return innings[inning_number - 1]

    def snapshot(self) -> ScoreSnapshot:
        """Create an immutable snapshot of the current score."""
        return ScoreSnapshot(
            away_innings=tuple(self._away_innings),
            home_innings=tuple(self._home_innings),
            away_total=self.away,
            home_total=self.home,
        )

    # ---------- Mutations ----------

    def ensure_inning(self, inning_number: int) -> None:
        """
        Ensure that innings exist up to the given inning number.

        Args:
            inning_number: The inning number to ensure (1-indexed)

        Raises:
            ValueError: If inning_number is less than 1
        """
        self._validate_inning_number(inning_number)

        while len(self._away_innings) < inning_number:
            self._away_innings.append(0)
        while len(self._home_innings) < inning_number:
            self._home_innings.append(0)

    def score_run(self, *, top: bool, inning_number: int, runs: int = 1) -> None:
        """
        Score one or more runs for a team in a specific inning.

        Args:
            top: True for away team (top half), False for home team (bottom half)
            inning_number: The inning number (1-indexed)
            runs: Number of runs to score (default 1)

        Raises:
            ValueError: If inning_number < 1 or runs < 0
        """
        self._validate_inning_number(inning_number)

        if runs < 0:
            raise ValueError(f"Cannot score negative runs: {runs}")

        if runs == 0:
            return  # Nothing to do

        self.ensure_inning(inning_number)

        if top:
            self._away_innings[inning_number - 1] += runs
        else:
            self._home_innings[inning_number - 1] += runs

    def clear(self) -> None:
        """Reset the score to 0-0 (clear all innings)."""
        self._away_innings.clear()
        self._home_innings.clear()

    # ---------- Validation ----------

    @staticmethod
    def _validate_inning_number(inning_number: int) -> None:
        """
        Validate that inning number is valid.

        Raises:
            TypeError: If inning_number is not an integer
            ValueError: If inning_number is less than 1
        """
        if not isinstance(inning_number, int):
            raise TypeError(
                f"Inning number must be an integer, got {type(inning_number).__name__}"
            )
        if inning_number < 1:
            raise ValueError(f"Inning number must be at least 1, got {inning_number}")

    # ---------- String Representation ----------

    def __str__(self) -> str:
        """Return the score as a string."""
        return f"\nHome:    {self.home}\nVisitor: {self.away}\n"

    def __repr__(self) -> str:
        """Return a detailed representation."""
        return f"Score(home={self.home}, away={self.away})"

    def scoreboard(self, max_innings: int = 9) -> str:
        """
        Return a formatted scoreboard showing runs by inning.

        Args:
            max_innings: Number of innings to display (default 9)

        Returns:
            A multi-line string showing the scoreboard
        """
        # Determine how many innings to show
        innings_played = max(
            len(self._away_innings), len(self._home_innings), max_innings
        )

        # Build header
        header = "    |"
        for i in range(1, innings_played + 1):
            header += f" {i:2} |"
        header += "  R |"

        # Build away row
        away_row = "Away|"
        for i in range(1, innings_played + 1):
            runs = self.runs_in_inning(i, top=True)
            if i <= len(self._away_innings):
                away_row += f" {runs:2} |"
            else:
                away_row += "    |"
        away_row += f" {self.away:2} |"

        # Build home row
        home_row = "Home|"
        for i in range(1, innings_played + 1):
            runs = self.runs_in_inning(i, top=False)
            if i <= len(self._home_innings):
                home_row += f" {runs:2} |"
            else:
                home_row += "    |"
        home_row += f" {self.home:2} |"

        # Build separator
        separator = "----+" + ("-" * 5 + "+") * innings_played + "-----+"

        return f"\n{header}\n{separator}\n{away_row}\n{home_row}\n"
