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
        self.lineup = Lineup()


class Lineup(object):
    """A team lineup."""
    def __init__(self):
        self.batting_order = []
        self.pitcher = None
        self.catcher = None
        self.first = None
        self.second = None
        self.third = None
        self.short = None
        self.left = None
        self.center = None
        self.right = None
