class Score(object):
    """Keep track of the score."""

    def __init__(self):
        self.away_innings = [0]
        self.home_innings = []

    def __str__(self):
        """Return the score as a string."""
        output = "\n"
        output += "Home:    " + str(self.home) + "\n"
        output += "Visitor: " + str(self.away) + "\n"
        return output

    @property
    def away(self):
        """Return the away score."""
        return sum(self.away_innings)

    @property
    def home(self):
        """Return the home score."""
        return sum(self.home_innings)

    @property
    def top(self):
        if len(self.away_innings) == len(self.home_innings):
            return False
        else:
            return True

    def score_run(self):
        """Add a run to the last inning in list."""
        if self.top:
            self.away_innings[-1] += 1
        else:
            self.home_innings[-1] += 1

    def new_inning(self):
        """Add a new inning score to the list."""
        if self.top:
            self.home_innings.append(0)
        else:
            self.away_innings.append(0)
