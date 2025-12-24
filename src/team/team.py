"""The team class.

Basically, a city, a mascot and a list of players.

"""

import csv

from src.stats import stats
from src.player.player import Player
from . import SKILL_MAP

__author__ = "josh"


class Team(object):
    """A Baseball Team class."""

    def __init__(self, city, mascot):
        # self.players = self.load_team()
        self.city = city
        self.mascot = mascot

        self.batter_index = 0  # index on the lineup
        self.current_pitcher_index = 0  # index on the roster (players)
        self.stats = stats.TeamStats()
        self.score = 0
        self.players = []
        # TODO this isn't right
        self.lineup = self.players

    def load_team(
        self,
        path="FooBars.csv",
    ):
        """Load a team from a csv file."""
        self.team_file = path
        players = []

        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                first_name, last_name = row["Name"].split(" ", 1)
                player = Player(
                    first_name=first_name.title(),
                    last_name=last_name.title(),
                    throws=row["T"] or None,
                    bats=row["B"] or None,
                    position=row["PS"] or None,
                )
                for csv_key, skill_name in SKILL_MAP.items():
                    value = row.get(csv_key)
                    if value:
                        player.skills[skill_name] = int(value)
                    else:
                        player.skills[skill_name] = 0
                players.append(player)
        self.players = players

    def set_lineup(self):
        """Set the batting lineup and positions."""

        # TODO this isn't right
        self.lineup = self.players

    def current_batter(self):
        return self.lineup[self.batter_index]

    def next_batter(self):
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter()

    def current_pitcher(self):
        return self.players[self.current_pitcher_index]

    def score_run(self):
        self.score += 1
