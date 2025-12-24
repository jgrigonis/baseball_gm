# lineup.py
class Lineup(object):
    """
    The lineup for a team.
    """

    def __init__(self, dh=False, home=True):
        self.dh = dh
        self.home = home  # Home or Visitor
        self.batting_order = [None for _ in range(9)]
        self.positions = {
            "pitcher": None,
            "catcher": None,
            "first": None,
            "second": None,
            "third": None,
            "short": None,
            "left": None,
            "center": None,
            "right": None,
        }
        self.subs = []
        self.unavailable = []

    def __str__(self):
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

    def next_batter(self):
        pass

    def relief_pitcher(self):
        pass

    def double_switch(self):
        pass

    def pinch_hitter(self):
        pass

    def pinch_runner(self):
        pass
