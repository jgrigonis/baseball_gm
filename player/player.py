import names


class Player(object):
    """A Baseball Player class."""
    def __init__(self, first_name, last_name):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        self.skills = {
            'accuracy': 50,      # Pitching accuracy
            'stamina': 50,       # Pitching stamina
            'recovery': 50,      # Pitching stamina recovery speed with rest
            'clutch': 50,        # Clutch
            'power': 50,         # Hitting power
            'eye': 50,           # Eye
            'contact': 50,       # Batting contact
            'speed': 50,         # Running speed
            'base_running': 50,  # Base-running skill
            'bunting': 50,       # Bunting
        }

