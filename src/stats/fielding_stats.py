class FieldingStats(object):
    """The fielding statistics object."""

    def __init__(self):
        """Initialize the fielding statistics."""
        self.putouts = 0
        self.assists = 0
        self.errors = 0
        self.chances = 0  # putouts + assists + errors
        self.passed_balls = 0
        self.catcher_interferences = 0

    def __repr__(self):
        """Return the representation of the fielding statistics."""
        return f"<FieldingStats PO={self.putouts} " f"A={self.assists} E={self.errors}>"

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
        """Add the fielding statistics from another object."""
        for attr in vars(self):
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
        """Add an error."""
        self.passed_balls += 1
        self.chances += 1

    def catcher_interference(self):
        """Add a catcher interference."""
        self.catcher_interferences += 1
        self.error()
