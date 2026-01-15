# src/game/inning.py
import src.game.game_exceptions as game_exceptions


class Inning(object):
    """Keep track of inning related information."""

    def __init__(self):
        """Set up a new inning.  Start in the top of the 1st with no outs."""
        self.number = 1
        self.top = True
        self.outs = 0

    @property
    def bottom(self):
        return not self.top

    def __str__(self):
        """Return an inning string."""
        output = ""
        if self.top:
            return f"Top of {self.number}"
            # output += "Top of "
        else:
            return f"Bottom of {self.number}"
            # output += "Bottom of "
        # output += str(self.number)
        # return output

    def increment(self):
        """Move to the next half inning."""
        if self.top:
            self.top = False
        else:
            self.top = True
            self.number += 1
        self.reset_outs()

    def record_out(self, n: int = 1):
        self.outs += n

    # def out(self):
    #     """Get an out."""
    #     self.outs += 1
    #     if self.outs >= 3:
    #         raise game_exceptions.TooManyOuts()

    def reset_outs(self):
        """Set the outs to zero."""
        self.outs = 0
