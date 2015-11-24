class Player(object):
    """A Baseball Player class."""
    def __init__(self, first_name=None, last_name=None):
        """Setup the player."""
        if first_name is None:
            self.first_name = "Random"
        else:
            self.first_name = first_name
        if last_name is None:
            self.last_name = "Name"
        else:
            self.last_name = last_name
