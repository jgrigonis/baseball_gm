"""The team class.

Basically, a city, a mascot and a list of players.

"""
__author__ = 'josh'


class Team(object):
    """A Baseball Team class."""
    def __init__(self, city, mascot):
        self.city = city
        self.mascot = mascot
        self.players = []
        self.batting_order = [None for _ in range(9)]
        self.positions = {
            'pitcher': None,
            'catcher': None,
            'first': None,
            'second': None,
            'third': None,
            'short': None,
            'left': None,
            'center': None,
            'right': None,
        }
        self.subs = []
        self.unavailable = []

    def load_team(self):
        """Load a team from a csv file."""
        pass

    def set_lineup(self):
        """Set the lineup."""
        pass

    def verify_lineup(self):
        if len(self.batting_order) != 9:
            return False
        for position in self.positions:
            if position is None:
                return False
        # Check for duplicates at position.
        # Check that each position player is in the batting_order
        # check for None in batting order

        return True

    def set_position(self, player, position):
        pass

    def set_batting_order(self, player, number):
        pass
