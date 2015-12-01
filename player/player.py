class Player(object):
    """A Baseball Player class."""
    def __init__(self, first_name, last_name):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        # May be desirable to split skills between pitching and batting
        self.skills = {
            'accuracy': 0,      # Pitching accuracy
            'stamina': 0,       # Pitching stamina
            'recovery': 0,      # Pitching stamina recovery speed with rest
            'clutch': 0,        # Clutch
            'power': 0,         # Hitting power
            'eye': 0,           # Eye
            'contact': 0,       # Batting contact
            'speed': 0,         # Running speed
            'base_running': 0,  # Base-running skill
            'bunting': 0,       # Bunting
        }

