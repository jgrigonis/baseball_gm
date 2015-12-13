"""The player class.

To add:
Different position players should have different mean values for
different skills, e.g. 1st and 3rd should have more power
middle infielders less
outfielders should be faster
etc.

player should also get stats.

Calculate an overall value based on weighted combination of skills.
e.g. bunting is worth less than power.

"""
import game.game_exceptions as game_exceptions
import random


class Player(object):
    """A Baseball Player class."""
    def __init__(self, first_name, last_name, throws=None, bats=None,
                 position=None):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        self.throws = throws        # right or left or None
        self.bats = bats            # right, left or switch or None
        self.position = position    # Just used for setting skills
        self.skills = {
            # pitching
            'accuracy': 0,      # Pitching accuracy
            'stamina': 0,       # Pitching stamina
            'recovery': 0,      # Pitching stamina recovery speed with rest
            # general
            'clutch': 0,        # Clutch
            'speed': 0,         # Running speed
            # hitting
            'power': 0,         # Hitting power
            'eye': 0,           # Eye
            'contact': 0,       # Batting contact
            'base_running': 0,  # Base-running skill
            'bunting': 0,       # Bunting
            # defensive
            'catching': 0,      # Skill as a catcher
            'infield': 0,       # In-fielding skill
            'outfield': 0,      # Fly-ball catching
            'arm': 0,           # Arm strength
        }
        self.template = {
            'sp': {
                'throws_left': 0.25,
                'switch_hitter': 0.01,
                'bats_left': 0.01,
                'accuracy': 60,
                'stamina': 70,
                'recovery': 60,
                'power': 20,
                'eye': 30,
                'contact': 30,
                'base_running': 40,
                'catching': 20,
                'outfield': 40,
                'arm': 60
            },
            'rp': {
                'throws_left': 0.35,
                'switch_hitter': 0.01,
                'bats_left': 0.01,
                'accuracy': 60,
                'recovery': 60,
                'power': 20,
                'eye': 30,
                'contact': 30,
                'base_running': 40,
                'catching': 20,
                'outfield': 40,
                'arm': 60
            },
            'c': {
                'throws_left': 0.001,
                'switch_hitter': 0.16,
                'bats_left': 0.12,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'base_running': 40,
                'catching': 70,
                'outfield': 40,
                'arm': 60
            },
            '1b': {
                'throws_left': 0.33,
                'switch_hitter': 0.12,
                'bats_left': 0.12,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 30,
                'power': 60,
                'base_running': 40,
                'outfield': 40,
            },
            'ss': {
                'throws_left': 0.001,
                'switch_hitter': 0.25,
                'bats_left': 0.05,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 60,
                'power': 35,
                'infield': 70,
            },
            '2b': {
                'throws_left': 0.001,
                'switch_hitter': 0.25,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 60,
                'power': 35,
                'infield': 70,
            },
            '3b': {
                'throws_left': 0.001,
                'switch_hitter': 0.15,
                'bats_left': 0.05,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'infield': 60,
            },
            'lf': {
                'throws_left': 0.25,
                'switch_hitter': 0.10,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 60,
                'power': 60,
                'catching': 40,
                'infield': 40,
                'outfield': 60,
            },
            'cf': {
                'throws_left': 0.33,
                'switch_hitter': 0.16,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 65,
                'catching': 40,
                'infield': 40,
                'outfield': 65,
                'arm': 60,
            },
            'rf': {
                'throws_left': 0.25,
                'switch_hitter': 0.1,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 60,
                'power': 60,
                'catching': 40,
                'infield': 40,
                'outfield': 60,
                'arm': 60,
            },
            'if': {
                'throws_left': 0.001,
                'switch_hitter': 0.25,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'infield': 60,
            },
            'of': {
                'throws_left': 0.3,
                'switch_hitter': 0.2,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'speed': 55,
                'catching': 40,
                'infield': 40,
                'outfield': 60,
            },
            'dh': {
                'throws_left': 0.33,
                'switch_hitter': 0.15,
                'bats_left': 0.2,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'power': 65,
                'catching': 40,
                'infield': 40,
                'outfield': 40,
                'arm': 40,
            },
        }

    def __str__(self):
        """Output the player name as a string."""
        output = str(self.first_name + ' ' + self.last_name) + "\n"
        if self.position is not None:
            output += "position: {0:>{1}}\n".format(self.position, 17)
        if self.throws is not None:
            output += "throws: {0:>{1}}\n".format(self.throws, 19)
        if self.bats is not None:
            output += "bats: {0:>{1}}\n".format(self.bats, 21)
        for key in self.skills.keys():
            output += str("{0}: {1:>{2}}").format(key,
                                                  self.skills[key],
                                                  25 - len(key))
            output += "\n"
        return output

    @staticmethod
    def generate_stat(minimum=1, maximum=100, mean=50, sigma=None):
        """
        :param minimum: minimum allowable value for stat. Must be
            greater than 0
        :param maximum: maximum allowable value for stat. Must be
            greater than minimum
        :param mean: the mean value for the stat to be generated.
            Must be between minimum and maximum
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

    def apply_position_template(self):
        """Based on the position, set stats and characteristics
        according to the template.
        """
        if self.throws is None:
            # chance of throwing lefty
            if random.random() > \
                    self.template[self.position].get('throws_left', 0.21):
                self.throws = 'right'
            else:
                self.throws = 'left'
        if self.bats is None:
            # chance of being a switch hitter.
            if random.random() < \
                    self.template[self.position].get('switch_hitter', 0.09):
                self.bats = 'switch'
            # chance of batting opposite
            elif random.random() > \
                    self.template[self.position].get('bats_left', 0.1):
                self.bats = self.throws
            else:
                self.bats = 'left'
        for skill in self.skills:
            self.skills[skill] = self.generate_stat(
                mean=self.template[self.position].get(skill, 50))
        if self.throws == 'left':
            self.skills['catching'] = self.generate_stat(mean=10)

    def generate(self):
        """Generate random stats, and characteristics, based on a
        position type.

        """
        positions = ['sp',  # starting pitcher
                     'rp',  # relief pitcher
                     'c',   # catcher
                     '1b',  # first baseman
                     '2b',  # second baseman
                     'ss',  # shortstop
                     '3b',  # third baseman
                     'lf',  # left fielder
                     'cf',  # center fielder
                     'rf',  # right fielder
                     'if',  # utility infielder
                     'of',  # outfielder
                     'dh',  # designated hitter
                     ]
        if self.position is None:
            self.position = random.choice(positions)
        elif self.position not in positions:
            raise game_exceptions.BadPositionException()
        self.apply_position_template()
