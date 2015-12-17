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
from player import positions


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
        self.ratings = dict()       # Will be populated based on skills
        self.skills = {
            # pitching
            'accuracy': 0,      # Pitching accuracy
            'stamina': 0,       # Pitching stamina
            'recovery': 0,      # Pitching stamina recovery speed with rest
            'ground_balls': 0,  # Ground ball pitcher
            'strikes': 0,       # Pitcher ability to get strikes
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
                'infield': 60,
            },
            'lf': {
                'throws_left': 0.25,
                'switch_hitter': 0.10,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
                'infield': 60,
            },
            'of': {
                'throws_left': 0.3,
                'switch_hitter': 0.2,
                'bats_left': 0.15,
                'accuracy': 10,
                'stamina': 10,
                'recovery': 10,
                'ground_balls': 10,
                'strikes': 10,
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
                'ground_balls': 10,
                'strikes': 10,
                'power': 65,
                'catching': 40,
                'infield': 40,
                'outfield': 40,
                'arm': 40,
            },
        }

    def __str__(self):
        """Output the player name as a multi-line string."""
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
        output += "\n"
        for key in self.ratings.keys():
            output += str("{0}: {1:>{2}}").format(key,
                                                  self.ratings[key],
                                                  25 - len(key))
            output += "\n"
        return output

    def horizontal(self):
        """Output the player and stats as a single line."""
        name = self.first_name + ' ' + self.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name
        output += "{:>{}}".format(self.position, 3)
        output += "{:>{}}".format(self.abbreviate(self.throws), 2)
        output += "{:>{}}".format(self.abbreviate(self.bats), 2)
        output += "{:>{}}".format(self.skills["clutch"], 3)
        output += "{:>{}}".format(self.skills["speed"], 3)
        output += "{:>{}}".format(self.skills["power"], 3)
        output += "{:>{}}".format(self.skills["eye"], 3)
        output += "{:>{}}".format(self.skills["contact"], 3)
        output += "{:>{}}".format(self.skills["base_running"], 3)
        output += "{:>{}}".format(self.skills["bunting"], 3)
        output += "{:>{}}".format(self.skills["catching"], 3)
        output += "{:>{}}".format(self.skills["infield"], 3)
        output += "{:>{}}".format(self.skills["outfield"], 3)
        output += "{:>{}}".format(self.skills["arm"], 3)
        output += "{:>{}}".format(self.skills["accuracy"], 3)
        output += "{:>{}}".format(self.skills["stamina"], 3)
        output += "{:>{}}".format(self.skills["recovery"], 3)
        output += "{:>{}}".format(self.skills["ground_balls"], 3)
        output += "{:>{}}".format(self.skills["strikes"], 3)
        output += "  "
        output += "{:>{}}".format(self.ratings["p"], 3)
        output += "{:>{}}".format(self.ratings["c"], 3)
        output += "{:>{}}".format(self.ratings["1b"], 3)
        output += "{:>{}}".format(self.ratings["2b"], 3)
        output += "{:>{}}".format(self.ratings["3b"], 3)
        output += "{:>{}}".format(self.ratings["ss"], 3)
        output += "{:>{}}".format(self.ratings["lf"], 3)
        output += "{:>{}}".format(self.ratings["cf"], 3)
        output += "{:>{}}".format(self.ratings["rf"], 3)
        output += " "
        output += "{:>{}}".format(self.ratings["lead_off"], 3)
        output += "{:>{}}".format(self.ratings["contact_hitter"], 3)
        output += "{:>{}}".format(self.ratings["power_hitter"], 3)
        return output

    @staticmethod
    def header():
        """Return the header as a single line."""
        output = str("{:<{}} ".format("Name", 30))  # 30 is the longest name
        output += "{:>{}}".format("PS", 3)
        output += "{:>{}}".format("T", 2)
        output += "{:>{}}".format("B", 2)
        output += "{:>{}}".format("CL", 3)
        output += "{:>{}}".format("SP", 3)
        output += "{:>{}}".format("PO", 3)
        output += "{:>{}}".format("EY", 3)
        output += "{:>{}}".format("CT", 3)
        output += "{:>{}}".format("BR", 3)
        output += "{:>{}}".format("BU", 3)
        output += "{:>{}}".format("CA", 3)
        output += "{:>{}}".format("IF", 3)
        output += "{:>{}}".format("OF", 3)
        output += "{:>{}}".format("AR", 3)
        output += "{:>{}}".format("AC", 3)
        output += "{:>{}}".format("ST", 3)
        output += "{:>{}}".format("RE", 3)
        output += "{:>{}}".format("GB", 3)
        output += "{:>{}}".format("KK", 3)
        output += "  "
        output += "{:>{}}".format("P", 3)
        output += "{:>{}}".format("C", 3)
        output += "{:>{}}".format("1B", 3)
        output += "{:>{}}".format("2B", 3)
        output += "{:>{}}".format("3B", 3)
        output += "{:>{}}".format("SS", 3)
        output += "{:>{}}".format("LF", 3)
        output += "{:>{}}".format("CF", 3)
        output += "{:>{}}".format("RF", 3)
        output += " "
        output += "{:>{}}".format("LO", 3)
        output += "{:>{}}".format("CH", 3)
        output += "{:>{}}".format("PH", 3)
        return output

    @staticmethod
    def abbreviate(value):
        if value == 'right':
            return 'r'
        if value == 'left':
            return 'l'
        if value == 'switch':
            return 's'

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
                # No bats right, throws left, except Rickey
                self.bats = 'left'
        for skill in self.skills:
            self.skills[skill] = self.generate_stat(
                mean=self.template[self.position].get(skill, 50))
        # No left handed catchers, please
        if self.throws == 'left':
            self.skills['catching'] = self.generate_stat(mean=10)

    def generate(self):
        """Generate random stats, and characteristics, based on a
        position type.

        """
        if self.position is None:
            self.position = random.choice(positions)
        elif self.position not in positions:
            raise game_exceptions.BadPositionException()
        self.apply_position_template()
        self.rate_player()

    def rate_player(self):
        """Based on the player skills, rate the player at various
        positions and hitting styles. For instance, an outfielder's
        skill in the outfield is not just their 'outfield' rating,
        their speed, arm and clutch skill also come into play.

        Their speed will increase their range, their arm will increase
        the chance of putting out runners stretching hits, and clutch
        will increase the chances of them making a game changing play
        in the clutch.
        """
        self.ratings["cf"] = int(round(
            (self.skills.get("outfield") * 5 +
             self.skills.get("arm") * 2 +
             self.skills.get("speed") * 3 +
             self.skills.get("clutch")) / 11.0))
        self.ratings["rf"] = int(round(
            (self.skills.get("outfield") * 5 +
             self.skills.get("arm") * 2 +
             self.skills.get("speed") +
             self.skills.get("clutch")) / 9.0))
        self.ratings["lf"] = int(round(
            (self.skills.get("outfield") * 5 +
             self.skills.get("arm") +
             self.skills.get("speed") +
             self.skills.get("clutch")) / 8.0))
        self.ratings["c"] = int(round(
            (self.skills.get("catching") * 5 +
             self.skills.get("arm") +
             self.skills.get("clutch")) / 7.0))
        self.ratings["1b"] = int(round(
            (self.skills.get("infield") * 5 +
             self.skills.get("clutch")) / 6.0))
        self.ratings["2b"] = int(round(
            (self.skills.get("infield") * 5 +
             self.skills.get("speed") +
             self.skills.get("clutch")) / 7.0))
        self.ratings["ss"] = int(round(
            (self.skills.get("infield") * 5 +
             self.skills.get("speed") +
             self.skills.get("arm") +
             self.skills.get("clutch")) / 8.0))
        self.ratings["3b"] = int(round(
            (self.skills.get("infield") * 5 +
             self.skills.get("arm") +
             self.skills.get("clutch")) / 7.0))
        self.ratings["p"] = int(round(
            (self.skills.get("accuracy") +
             self.skills.get("stamina") +
             self.skills.get("recovery") +
             self.skills.get("ground_balls") +
             self.skills.get("strikes") +
             self.skills.get("clutch")) / 6.0))
        self.ratings["lead_off"] = int(round(
            (self.skills.get("speed") +
             self.skills.get("eye") * 2 +
             self.skills.get("contact") * 2 +
             self.skills.get("base_running") +
             self.skills.get("clutch")) / 7.0))
        self.ratings["contact_hitter"] = int(round(
            (self.skills.get("eye") * 2 +
             self.skills.get("contact") * 4 +
             self.skills.get("clutch")) / 7.0))
        self.ratings["power_hitter"] = int(round(
            (self.skills.get("power") * 4 +
             self.skills.get("eye") +
             self.skills.get("contact") +
             self.skills.get("clutch")) / 7.0))
