"""
The player class.

Calculate an overall value based on weighted combination of skills.
e.g. bunting is worth less than power.

"""

import random
import uuid

import src.game.game_exceptions as game_exceptions
import src.stats.stats as stats

# from src.player.player_formatters import PlayerFormatter
# from src.player.player_formatters import PlayerTableFormatter
from src.player.positions import positions, template, skill_template, skills


class Player(object):
    """A Baseball Player class."""

    def __init__(
        self,
        first_name: str,
        last_name: str,
        throws: str | None = None,
        bats: str | None = None,
        position: str | None = None,
        id: str | None = None,
    ):
        """Setup the player."""
        self.first_name = first_name
        self.last_name = last_name
        self.throws = throws  # right or left or None
        self.bats = bats  # right, left or switch or None
        self.position = position  # Just used for setting skills,
        # players can play any position during the game, they may just be bad at it
        self.id = id or uuid.uuid4().hex

        self.ratings = {}  # Will be populated based on skills
        self.skills = dict(skills)  # All the general baseball skills
        self.stats = stats.Stats()
        self.season_stats = stats.SeasonStats()
        self.career_stats = stats.CareerStats()

    def __str__(self):
        return f"<Player {self.name}>"

    @property
    def name(player):
        return f"{player.first_name} {player.last_name}"

    def aggregate_game(self):
        """Aggregate the game stats."""
        self.season_stats.add_game(self.stats)

    def init_stats(self):
        self.stats = stats.Stats()

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

        Generate one stat.  Generally, skills will have a mean
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
            if random.random() > template[self.position].get("throws_left", 0.21):
                self.throws = "right"
            else:
                self.throws = "left"
        if self.bats is None:
            # chance of being a switch hitter
            if random.random() < template[self.position].get("switch_hitter", 0.09):
                self.bats = "switch"
            # chance of batting opposite (10%)
            elif random.random() > template[self.position].get("bats_left", 0.1):
                self.bats = self.throws
            else:
                # No one bats right, throws left, except Rickey
                self.bats = "left"

    def apply_skill_template(self):
        """
        Based on the position, set skills
        according to the skill_template.

        """
        for skill in self.skills:
            self.skills[skill] = self.generate_stat(
                mean=skill_template[self.position].get(skill, 50)
            )
        # No left handed catchers, please
        if self.throws == "left":
            self.skills["catching"] = self.generate_stat(mean=10)

    def generate(self):
        """
        Generate random skills, and characteristics, based on a
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
        self.ratings["cf"] = int(
            round(
                (
                    self.skills.get("outfield") * 5
                    + self.skills.get("arm") * 2
                    + self.skills.get("speed") * 3
                    + self.skills.get("clutch")
                )
                / 11.0
            )
        )
        self.ratings["rf"] = int(
            round(
                (
                    self.skills.get("outfield") * 5
                    + self.skills.get("arm") * 2
                    + self.skills.get("speed")
                    + self.skills.get("clutch")
                )
                / 9.0
            )
        )
        self.ratings["lf"] = int(
            round(
                (
                    self.skills.get("outfield") * 5
                    + self.skills.get("arm")
                    + self.skills.get("speed")
                    + self.skills.get("clutch")
                )
                / 8.0
            )
        )
        self.ratings["c"] = int(
            round(
                (
                    self.skills.get("catching") * 5
                    + self.skills.get("arm")
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        self.ratings["1b"] = int(
            round((self.skills.get("infield") * 5 + self.skills.get("clutch")) / 6.0)
        )
        self.ratings["2b"] = int(
            round(
                (
                    self.skills.get("infield") * 5
                    + self.skills.get("speed")
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        self.ratings["ss"] = int(
            round(
                (
                    self.skills.get("infield") * 5
                    + self.skills.get("speed")
                    + self.skills.get("arm")
                    + self.skills.get("clutch")
                )
                / 8.0
            )
        )
        self.ratings["3b"] = int(
            round(
                (
                    self.skills.get("infield") * 5
                    + self.skills.get("arm")
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        self.ratings["p"] = int(
            round(
                (
                    self.skills.get("accuracy")
                    + self.skills.get("stamina")
                    + self.skills.get("recovery")
                    + self.skills.get("ground_balls")
                    + self.skills.get("strikes")
                    + self.skills.get("clutch")
                )
                / 6.0
            )
        )
        self.ratings["lead_off"] = int(
            round(
                (
                    self.skills.get("speed")
                    + self.skills.get("eye") * 2
                    + self.skills.get("contact") * 2
                    + self.skills.get("base_running")
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        self.ratings["contact_hitter"] = int(
            round(
                (
                    self.skills.get("eye") * 2
                    + self.skills.get("contact") * 4
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        self.ratings["power_hitter"] = int(
            round(
                (
                    self.skills.get("power") * 4
                    + self.skills.get("eye")
                    + self.skills.get("contact")
                    + self.skills.get("clutch")
                )
                / 7.0
            )
        )
        # Lefties do not play these positions.
        if self.throws == "left":
            self.ratings["c"] = int(round(self.ratings["c"] / 2.0))
            self.ratings["2b"] = int(round(self.ratings["2b"] / 2.0))
            self.ratings["ss"] = int(round(self.ratings["ss"] / 2.0))
            self.ratings["3b"] = int(round(self.ratings["3b"] / 2.0))
