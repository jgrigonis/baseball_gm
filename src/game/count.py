"""The Count class.  Keep track of balls and strikes."""


class Count(object):
    """Keep track of the count."""
    def __init__(self):
        """Initialize balls and strikes to 0."""
        self.balls = 0
        self.strikes = 0

    def __str__(self):
        """Output the count as a string."""
        return "%s balls, %s strikes" % (self.balls, self.strikes)

    def reset_count(self):
        """Reset the balls and strikes to zero."""
        self.balls = 0
        self.strikes = 0

    def strike(self):
        """
        Get a strike.

        Increment the strike count if it's less than 2.  Otherwise,
        reset the count.

        """
        if self.strikes < 2:
            self.strikes += 1
        else:
            self.reset_count()

    def ball(self):
        """
        Get a ball.

        Increment the ball count if it's less than 3.  Otherwise,
        reset the count.

        """
        if self.balls < 3:
            self.balls += 1
        else:
            self.reset_count()
