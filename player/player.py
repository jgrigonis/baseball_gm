"""The player class.

To add: position skills, throwing arm, batting side
Different position players should have different mean values for
different skills, e.g. 1st and 3rd should have more power
middle infielders less
outfielders should be faster
etc.

player should also get stats.

Calculate an overall value based on weighted combination of skills.
e.g. bunting is worth less than power.

"""
import random


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

    @staticmethod
    def generate_stat(minimum=0, maximum=100, mean=50, sigma=None):
        """
        :param minimum: minimum allowable value for stat.
        :param maximum: maximum allowable value for stat.
        :param mean: the mean value for the stat to be generated.
        :param sigma: standard deviation. If unspecified, will vary
            based on min, max and mean.

        Generate one stat.  Generally, stats will have a mean
        value of 50.  The standard deviation, or sigma defaults to
        16.6667.  If you use a different mean, the sigma will shrink
        such that the 3rd standard deviation is the closer of max or
        min.  For example, if you use 70 for your mean, the sigma
        will be 10.  (100 - 70) / 3.

        """
        if sigma is None:
            if mean >= 50:
                sigma = (maximum - mean) / 3.0
            else:
                sigma = (mean - minimum) / 3.0
        stat = random.gauss(mean, sigma)
        if stat > maximum:
            return maximum
        elif stat < minimum:
            return minimum
        return int(stat)
