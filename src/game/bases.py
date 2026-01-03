import src.game.game_exceptions as game_exceptions


class Bases:
    """
    Represents the bases.

    Index mapping:
        0 -> first
        1 -> second
        2 -> third

    Home (3) is virtual and never stored.
    """

    def __init__(self):
        """Initialize the bases."""
        # Only first, second, third are stored
        self._bases = [0, 0, 0]

    def __str__(self):
        """Output as a string with runner names."""
        if self._bases == [0, 0, 0]:
            return "Bases empty."
        if self.men_on() == 1:
            if self._bases[0] != 0:
                runner = self._bases[0]
                return f"{runner.name} on first."
            elif self._bases[1] != 0:
                runner = self._bases[1]
                return f"{runner.name} on second."
            elif self._bases[2] != 0:
                runner = self._bases[2]
                return f"{runner.name} on third."
            else:
                return ""
        elif self.men_on() == 2:
            runners = []
            if self._bases[0] != 0:
                runners.append(f"{self._bases[0].name} on first")
            if self._bases[1] != 0:
                runners.append(f"{self._bases[1].name} on second")
            if self._bases[2] != 0:
                runners.append(f"{self._bases[2].name} on third")
            return ", ".join(runners) + "."
        elif self.men_on() == 3:
            return f"Bases loaded: {self._bases[0].name} on first, {self._bases[1].name} on second, {self._bases[2].name} on third."

    # ---------- Internal helpers ----------

    @staticmethod
    def _validate_base(base):
        """Validate the base."""
        if not isinstance(base, int):
            raise TypeError(f"Base must be int, got {type(base).__name__}")
        if base < 0 or base > 3:
            raise IndexError(f"Invalid base index: {base}")
        return base

    # ---------- Python container protocol ----------

    def __getitem__(self, base):
        """Get the runner on the base."""
        base = self._validate_base(base)
        if base == 3:
            raise IndexError("Home plate is not a valid base index")
        return self._bases[base]

    def __setitem__(self, base, value):
        """Set the runner on the base."""
        base = self._validate_base(base)
        if base == 3:
            raise IndexError("Cannot assign a runner to home plate")
        self._bases[base] = value

    # ---------- Public API ----------

    def clear(self, bases=None):
        """
        Clear one or more bases.

        bases: None, int, or iterable of ints
        """
        if bases is None:
            self._bases = [0, 0, 0]
            return

        if isinstance(bases, int):
            bases = [bases]

        for base in bases:
            base = self._validate_base(base)
            if base == 3:
                continue
            self._bases[base] = 0

    def empty_base(self, base):
        """Check if the base is empty."""
        base = self._validate_base(base)
        if base == 3:
            return True
        return self._bases[base] == 0

    def men_on(self):
        """Return the number of runners on base."""
        return sum(1 for b in self._bases if b != 0)

    def advance(self, base):
        """
        Advance runner from `base` to `base + 1`.
        Returns the scorer if the runner scores.
        """
        base = self._validate_base(base)
        runner = self._bases[base]
        if base == 2:
            return runner  # scores
        if self._bases[base + 1] != 0:
            raise game_exceptions.AdvanceToOccupiedBase()
        if runner == 0:
            raise game_exceptions.NoRunnerToAdvance()

        self._bases[base] = 0
        self._bases[base + 1] = runner
        return None

    def advance_all(self):
        """
        Advance all runners one base.
        Returns the scorer if one scores.
        """
        scorer = None

        for base in reversed(range(3)):
            runner = self._bases[base]
            if runner:
                self._bases[base] = 0
                if base == 2:
                    scorer = runner
                else:
                    self._bases[base + 1] = runner
        return scorer

    def advance_many(self, advances):
        """
        advances: list of (from_base, to_base) tuples
        Returns list of scorers.
        """
        scorers = []

        for start, end in advances:
            self._validate_base(start)
            self._validate_base(end)
        if start >= end:
            raise game_exceptions.InvalidAdvance()

        for start, end in sorted(advances, reverse=True):
            runner = self._bases[start]
            if runner == 0:
                raise game_exceptions.InvalidAdvance()

            self._bases[start] = 0
            if end >= 3:
                scorers.append(runner)
            else:
                self._bases[end] = runner

        return scorers
