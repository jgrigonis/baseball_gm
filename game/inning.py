import game_exceptions


class Inning(object):
    """Keep track of inning related information."""
    def __init__(self):
        """Set up a new inning.  Start in the top of the 1st with no outs."""
        self.number = 1
        self.top = True
        self.outs = 0

    # def __str__(self):
    #     """Output the inning information as a string."""
    #     if self.top:
    #         half = "top"
    #     else:
    #         half = "bottom"
    #     return "It's the %s of %s." % (half, self.number)

    def increment(self):
        """Move to the next half inning."""
        if self.top:
            self.top = False
        else:
            self.top = True
            self.number += 1
        self.reset_outs()

    def out(self):
        """Get an out."""
        self.outs += 1
        if self.outs >= 3:
            raise game_exceptions.TooManyOuts()

    def reset_outs(self):
        """Set the outs to zero."""
        self.outs = 0
