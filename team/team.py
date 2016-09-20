"""The team class.

Basically, a city, a mascot and a list of players.

"""
__author__ = 'jgrigonis'


class Team(object):
    """A Baseball Team class."""
    def __init__(self, city, mascot):
        self.city = city
        self.mascot = mascot
        self.players = []
        self.batting_order = []
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

    def set_lineup(self):
        """Set the lineup."""
        pass

    def verify_lineup(self):
        if len(self.batting_order) != 9:
            return False
        if len(self.batting_order) != len(set(self.lineup.batting_order)):
            return False
        # Check for duplicates at position.
        # Check that each position player is in the batting_order
        return True
