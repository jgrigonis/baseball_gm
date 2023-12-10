"""
The player class.

TODO:
player should also get stats.

Calculate an overall value based on weighted combination of skills.
e.g. bunting is worth less than power.

"""
import src.game.game_exceptions as game_exceptions
import random
from . import positions, template, skill_template, skills


class Player(object):
    """A Baseball Player class."""
    def __init__(
            self, 
            first_name, 
            last_name, 
            throws=None, 
            bats=None,
            position=None
        ):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        self.throws = throws        # right or left or None
        self.bats = bats            # right, left or switch or None
        self.position = position    # Just used for setting skills
        self.ratings = dict()       # Will be populated based on skills
        self.skills = dict(skills)  # All the general baseball skills

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
            output += str("{0}: {1:>{2}}").format(
                key,
                self.skills[key],
                25 - len(key)
            )
            output += "\n"
        output += "\n"
        for key in self.ratings.keys():
            output += str("{0}: {1:>{2}}").format(
                key,
                self.ratings[key],
                25 - len(key)
            )
            output += "\n"
        return output

    def horizontal(self):
        """Output the player and stats as a single line."""
        name = self.first_name + ' ' + self.last_name
        output = str("{:<{}} ".format(name, 30))  # 30 is the longest name
        output += "{:>{}}".format(self.position, 3)
        output += "{:>{}}".format(self.abbreviate(self.throws), 2)
        output += "{:>{}}".format(self.abbreviate(self.bats), 2)
        for item in [
                self.skills["clutch"], 
                self.skills["speed"],
                self.skills["power"], 
                self.skills["eye"],
                self.skills["contact"],
                self.skills["base_running"],
                self.skills["bunting"], 
                self.skills["catching"],
                self.skills["infield"], 
                self.skills["outfield"],
                self.skills["arm"], 
                self.skills["accuracy"],
                self.skills["stamina"], 
                self.skills["recovery"],
                self.skills["ground_balls"], 
                self.skills["strikes"],
            ]:
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in [
                self.ratings["p"],
                self.ratings["c"], 
                self.ratings["1b"],
                self.ratings["2b"], 
                self.ratings["3b"],
                self.ratings["ss"],
                self.ratings["lf"],
                self.ratings["cf"], 
                self.ratings["rf"],
            ]:
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in [
                self.ratings["lead_off"], 
                self.ratings["contact_hitter"],
                self.ratings["power_hitter"],
            ]:
            output += "{:>{}}".format(item, 3)
        return output

    def csv(self):
        """Output the player and stats as a single csv line."""
        name = self.first_name + ' ' + self.last_name
        output = str("{},".format(name))
        for item in [
                self.position, 
                self.abbreviate(self.throws),
                self.abbreviate(self.bats), 
                self.skills["clutch"],
                self.skills["speed"], 
                self.skills["power"],
                self.skills["eye"], 
                self.skills["contact"],
                self.skills["base_running"], 
                self.skills["bunting"],
                self.skills["catching"], 
                self.skills["infield"],
                self.skills["outfield"], 
                self.skills["arm"],
                self.skills["accuracy"], 
                self.skills["stamina"],
                self.skills["recovery"], 
                self.skills["ground_balls"],
                self.skills["strikes"], 
                self.ratings["p"],
                self.ratings["c"], 
                self.ratings["1b"],
                self.ratings["2b"], 
                self.ratings["3b"],
                self.ratings["ss"], 
                self.ratings["lf"],
                self.ratings["cf"], 
                self.ratings["rf"],
                self.ratings["lead_off"], 
                self.ratings["contact_hitter"],
                self.ratings["power_hitter"]
            ]:
            output += "{},".format(item)
        output += "\n"
        return output

    @staticmethod
    def legend():
        """return the legend as a string"""
        output = str("\nLegend:\n")
        output += str("---------------------------\n")
        output += str("PS = position\n")
        output += str("T  = throws\n")
        output += str("B  = bats\n")
        output += str("CL = clutch\n")
        output += str("SP = run speed\n")
        output += str("PO = batting power\n")
        output += str("EY = eye\n")
        output += str("CT = contact hitting\n")
        output += str("BR = base running\n")
        output += str("BU = bunting\n")
        output += str("CA = catching\n")
        output += str("IF = infield skills\n")
        output += str("OF = outfield skills\n")
        output += str("AR = throwing arm\n")
        output += str("AC = pitching accuracy\n")
        output += str("ST = pitching stamina\n")
        output += str("RE = pitching recovery\n")
        output += str("GB = pitching ground balls\n")
        output += str("PS = pitching strikes\n")
        output += str("\nP  = Pitcher rating\n")
        output += str("C  = Catcher rating\n")
        output += str("1B = First baseman rating\n")
        output += str("2B = Second baseman rating\n")
        output += str("3B = Third baseman rating\n")
        output += str("SS = Short stop rating\n")
        output += str("LF = Left field rating\n")
        output += str("CF = Center field rating\n")
        output += str("RF = Right field rating\n")
        output += str("\nLO = Lead off hitter rating\n")
        output += str("CH = Contact hitter rating\n")
        output += str("PH = Power hitter rating\n")
        return output

    @staticmethod
    def csv_header():
        """Return the header as a single csv line."""
        output = str("{},".format("Name"))  # 30 is the longest name
        for item in [
                "PS", "T", "B", "CL", "SP", "PO", "EY", "CT", "BR",
                "BU", "CA", "IF", "OF", "AR", "AC", "ST", "RE", "GB",
                "KK", "P", "C", "1B", "2B", "3B", "SS", "LF", "CF",
                "RF", "LO", "CH", "PH"
            ]:
            output += "{},".format(item)
        output += "\n"
        return output

    @staticmethod
    def header():
        """Return the header as a single line."""
        output = str("{:<{}} ".format("Name", 30))  # 30 is the longest name
        output += "{:>{}}".format("PS", 3)
        output += "{:>{}}".format("T", 2)
        output += "{:>{}}".format("B", 2)
        for item in [
                "CL", "SP", "PO", "EY", "CT", "BR", "BU", "CA", "IF",
                "OF", "AR", "AC", "ST", "RE", "GB", "KK"
            ]:
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]:
            output += "{:>{}}".format(item, 3)
        output += "  "
        for item in ["LO", "CH", "PH"]:
            output += "{:>{}}".format(item, 3)
        return output

    @staticmethod
    def abbreviate(value):
        if value == 'right':
            return 'r'
        if value == 'left':
            return 'l'
        if value == 'switch':
            return 's'
        return value

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
        """
        Based on the position, set characteristics
        according to the template.

        """
        if self.throws is None:
            # chance of throwing lefty
            if random.random() > \
                    template[self.position].get('throws_left', 0.21):
                self.throws = 'right'
            else:
                self.throws = 'left'
        if self.bats is None:
            # chance of being a switch hitter
            if random.random() < \
                    template[self.position].get('switch_hitter', 0.09):
                self.bats = 'switch'
            # chance of batting opposite (10%)
            elif random.random() > \
                    template[self.position].get('bats_left', 0.1):
                self.bats = self.throws
            else:
                # No one bats right, throws left, except Rickey
                self.bats = 'left'

    def apply_skill_template(self):
        """
        Based on the position, set stats
        according to the skill_template.

        """
        for skill in self.skills:
            self.skills[skill] = self.generate_stat(
                mean=skill_template[self.position].get(skill, 50))
        # No left handed catchers, please
        if self.throws == 'left':
            self.skills['catching'] = self.generate_stat(mean=10)

    def generate(self):
        """
        Generate random stats, and characteristics, based on a
        position type.

        """
        if self.position is None:
            self.position = random.choice(positions)
        elif self.position not in positions:
            raise game_exceptions.BadPositionException()
        self.apply_position_template()
        self.apply_skill_template()
        self.rate_player()

    def rate_player(self):
        """
        Based on the player skills, rate the player at various
        positions and hitting styles. For instance, an outfielder's
        skill in the outfield is not just their 'outfield' rating,
        their speed, arm and clutch skill also come into play.

        Their speed will increase their range, their arm will increase
        the chance of putting out runners stretching hits, and clutch
        will increase the chances of them making a game changing play
        in the clutch.
        
        """
        self.ratings["cf"] = int(round(
            (
                self.skills.get("outfield") * 5 +
                self.skills.get("arm") * 2 +
                self.skills.get("speed") * 3 +
                self.skills.get("clutch")
            ) / 11.0))
        self.ratings["rf"] = int(round(
            (
                self.skills.get("outfield") * 5 +
                self.skills.get("arm") * 2 +
                self.skills.get("speed") +
                self.skills.get("clutch")
            ) / 9.0))
        self.ratings["lf"] = int(round(
            (
                self.skills.get("outfield") * 5 +
                self.skills.get("arm") +
                self.skills.get("speed") +
                self.skills.get("clutch")
            ) / 8.0))
        self.ratings["c"] = int(round(
            (
                self.skills.get("catching") * 5 +
                self.skills.get("arm") +
                self.skills.get("clutch")
            ) / 7.0))
        self.ratings["1b"] = int(round(
            (
                self.skills.get("infield") * 5 +
                self.skills.get("clutch")
            ) / 6.0))
        self.ratings["2b"] = int(round(
            (
                self.skills.get("infield") * 5 +
                self.skills.get("speed") +
                self.skills.get("clutch")
            ) / 7.0))
        self.ratings["ss"] = int(round(
            (
                self.skills.get("infield") * 5 +
                self.skills.get("speed") +
                self.skills.get("arm") +
                self.skills.get("clutch")
            ) / 8.0))
        self.ratings["3b"] = int(round(
            (
                self.skills.get("infield") * 5 +
                self.skills.get("arm") +
                self.skills.get("clutch")
            ) / 7.0))
        self.ratings["p"] = int(round(
            (
                self.skills.get("accuracy") +
                self.skills.get("stamina") +
                self.skills.get("recovery") +
                self.skills.get("ground_balls") +
                self.skills.get("strikes") +
                self.skills.get("clutch")
            ) / 6.0))
        self.ratings["lead_off"] = int(round(
            (
                self.skills.get("speed") +
                self.skills.get("eye") * 2 +
                self.skills.get("contact") * 2 +
                self.skills.get("base_running") +
                self.skills.get("clutch")
            ) / 7.0))
        self.ratings["contact_hitter"] = int(round(
            (
                self.skills.get("eye") * 2 +
                self.skills.get("contact") * 4 +
                self.skills.get("clutch")
            ) / 7.0))
        self.ratings["power_hitter"] = int(round(
            (
                self.skills.get("power") * 4 +
                self.skills.get("eye") +
                self.skills.get("contact") +
                self.skills.get("clutch")
            ) / 7.0))
        # Lefties do not play these positions.
        if self.throws == "left":
            self.ratings["c"] = int(round(self.ratings["c"] / 2.0))
            self.ratings["2b"] = int(round(self.ratings["2b"] / 2.0))
            self.ratings["ss"] = int(round(self.ratings["ss"] / 2.0))
            self.ratings["3b"] = int(round(self.ratings["3b"] / 2.0))
