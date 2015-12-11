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
    def __init__(self, first_name, last_name, throws=None, bats=None):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        self.throws = throws    # right or left or None
        self.bats = bats        # right, left or switch or None
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

    def __str__(self):
        """Output the player name as a string."""
        output = str(self.first_name + ' ' + self.last_name) + "\n"
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

    def generate(self, position=None):
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
        if position is None:
            position = random.choice(positions)
        elif position not in positions:
            raise game_exceptions.BadPositionException()
        # remove repetition, this needs to be a function
        if position == 'sp':
            if self.throws is None:
                # 25% chance of starting pitcher being lefty
                if random.random() > 0.25:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 99% chance of not being a switch hitter.
                if random.random() > 0.99:
                    self.bats = 'switch'
                else:
                    # 1% chance of batting opposite
                    if random.random() > 0.01:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        else:
                            self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=60)
            self.skills['stamina'] = self.generate_stat(mean=70)
            self.skills['recovery'] = self.generate_stat(mean=60)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat()
            self.skills['power'] = self.generate_stat(mean=20)
            self.skills['eye'] = self.generate_stat(mean=30)
            self.skills['contact'] = self.generate_stat(mean=30)
            self.skills['base_running'] = self.generate_stat(mean=40)
            self.skills['bunting'] = self.generate_stat()
            self.skills['catching'] = self.generate_stat(mean=20)
            self.skills['infield'] = self.generate_stat()
            self.skills['outfield'] = self.generate_stat(mean=40)
            self.skills['arm'] = self.generate_stat()

        if position == 'rp':
            if self.throws is None:
                # 35% chance of relief pitcher being lefty
                if random.random() > 0.35:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 99% chance of not being a switch hitter.
                if random.random() > 0.99:
                    self.bats = 'switch'
                else:
                    # 1% chance of batting opposite
                    if random.random() > 0.01:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        else:
                            self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=60)
            self.skills['stamina'] = self.generate_stat()
            self.skills['recovery'] = self.generate_stat(mean=60)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat()
            self.skills['power'] = self.generate_stat(mean=20)
            self.skills['eye'] = self.generate_stat(mean=30)
            self.skills['contact'] = self.generate_stat(mean=30)
            self.skills['base_running'] = self.generate_stat(mean=40)
            self.skills['bunting'] = self.generate_stat()
            self.skills['catching'] = self.generate_stat(mean=20)
            self.skills['infield'] = self.generate_stat()
            self.skills['outfield'] = self.generate_stat(mean=40)
            self.skills['arm'] = self.generate_stat()

        if position == 'c':
            if self.throws is None:
                # 0.1% chance of catcher being lefty
                if random.random() > 0.001:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 84% chance of not being a switch hitter.
                if random.random() > 0.84:
                    self.bats = 'switch'
                else:
                    # 12% chance of batting opposite
                    if random.random() > 0.12:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefty catchers don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=30)
            self.skills['power'] = self.generate_stat()
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat(mean=40)
            self.skills['bunting'] = self.generate_stat()
            self.skills['catching'] = self.generate_stat(mean=70)
            self.skills['infield'] = self.generate_stat()
            self.skills['outfield'] = self.generate_stat(mean=40)
            self.skills['arm'] = self.generate_stat()

        if position == '1b':
            if self.throws is None:
                # 33% chance of being lefty
                if random.random() > 0.33:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 88% chance of not being a switch hitter.
                if random.random() > 0.88:
                    self.bats = 'switch'
                else:
                    # 12% chance of batting opposite
                    if random.random() > 0.12:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=30)
            self.skills['power'] = self.generate_stat(mean=60)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat(mean=40)
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat()
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat()
            self.skills['outfield'] = self.generate_stat(mean=40)
            self.skills['arm'] = self.generate_stat()

        if position == '2b':
            if self.throws is None:
                # 0.01% chance of being lefty
                if random.random() > 0.001:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 75% chance of not being a switch hitter.
                if random.random() > 0.75:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=60)
            self.skills['power'] = self.generate_stat(mean=30)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat()
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=70)
            self.skills['outfield'] = self.generate_stat()
            self.skills['arm'] = self.generate_stat()

        if position == 'ss':
            if self.throws is None:
                # 0.01% chance of being lefty
                if random.random() > 0.001:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 75% chance of not being a switch hitter.
                if random.random() > 0.75:
                    self.bats = 'switch'
                else:
                    # 5% chance of batting opposite
                    if random.random() > 0.5:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=60)
            self.skills['power'] = self.generate_stat(mean=30)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat()
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=70)
            self.skills['outfield'] = self.generate_stat()
            self.skills['arm'] = self.generate_stat()

        if position == '3b':
            if self.throws is None:
                # 0.01% chance of being lefty
                if random.random() > 0.001:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 85% chance of not being a switch hitter.
                if random.random() > 0.85:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat()
            self.skills['power'] = self.generate_stat()
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat()
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=60)
            self.skills['outfield'] = self.generate_stat()
            self.skills['arm'] = self.generate_stat()

        if position == 'lf':
            if self.throws is None:
                # 25% chance of being lefty
                if random.random() > 0.25:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 90% chance of not being a switch hitter.
                if random.random() > 0.90:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        # Unless they are Rickey
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=60)
            self.skills['power'] = self.generate_stat(mean=60)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat(mean=40)
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=40)
            self.skills['outfield'] = self.generate_stat(mean=60)
            self.skills['arm'] = self.generate_stat()

        if position == 'cf':
            if self.throws is None:
                # 33% chance of being lefty
                if random.random() > 0.33:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 84% chance of not being a switch hitter.
                if random.random() > 0.84:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=65)
            self.skills['power'] = self.generate_stat()
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat(mean=40)
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=40)
            self.skills['outfield'] = self.generate_stat(mean=65)
            self.skills['arm'] = self.generate_stat(mean=60)

        if position == 'rf':
            if self.throws is None:
                # 25% chance of being lefty
                if random.random() > 0.25:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 90% chance of not being a switch hitter.
                if random.random() > 0.90:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=60)
            self.skills['power'] = self.generate_stat(mean=60)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat(mean=40)
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=40)
            self.skills['outfield'] = self.generate_stat(mean=60)
            self.skills['arm'] = self.generate_stat(mean=60)

        if position == 'if':
            if self.throws is None:
                # 0.01% chance of being lefty
                if random.random() > 0.001:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 75% chance of not being a switch hitter.
                if random.random() > 0.75:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat()
            self.skills['power'] = self.generate_stat()
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat()
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=60)
            self.skills['outfield'] = self.generate_stat()
            self.skills['arm'] = self.generate_stat()

        if position == 'of':
            if self.throws is None:
                # 30% chance of being lefty
                if random.random() > 0.30:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 88% chance of not being a switch hitter.
                if random.random() > 0.88:
                    self.bats = 'switch'
                else:
                    # 15% chance of batting opposite
                    if random.random() > 0.15:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat(mean=55)
            self.skills['power'] = self.generate_stat()
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat(mean=40)
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=40)
            self.skills['outfield'] = self.generate_stat(mean=60)
            self.skills['arm'] = self.generate_stat()

        if position == 'dh':
            if self.throws is None:
                # 33% chance of being lefty
                if random.random() > 0.33:
                    self.throws = 'right'
                else:
                    self.throws = 'left'
            if self.bats is None:
                # 85% chance of not being a switch hitter.
                if random.random() > 0.85:
                    self.bats = 'switch'
                else:
                    # 20% chance of batting opposite
                    if random.random() > 0.20:
                        self.bats = self.throws
                    else:
                        if self.throws == 'right':
                            self.bats = 'left'
                        # else: lefties don't bat right
                        #     self.bats = 'right'
            self.skills['accuracy'] = self.generate_stat(mean=10)
            self.skills['stamina'] = self.generate_stat(mean=10)
            self.skills['recovery'] = self.generate_stat(mean=10)
            self.skills['clutch'] = self.generate_stat()
            self.skills['speed'] = self.generate_stat()
            self.skills['power'] = self.generate_stat(mean=65)
            self.skills['eye'] = self.generate_stat()
            self.skills['contact'] = self.generate_stat()
            self.skills['base_running'] = self.generate_stat()
            self.skills['bunting'] = self.generate_stat()
            if self.throws == 'right':
                self.skills['catching'] = self.generate_stat(mean=40)
            else:
                self.skills['catching'] = self.generate_stat(mean=10)
            self.skills['infield'] = self.generate_stat(mean=40)
            self.skills['outfield'] = self.generate_stat(mean=40)
            self.skills['arm'] = self.generate_stat(mean=40)
