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


    def load_team(self):
        """Load a team from a csv file."""
        pass
