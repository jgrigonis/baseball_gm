"""The team class.

Basically, a city, a mascot and a list of players.

"""

import csv

from src.stats import stats
from src.player.player import Player
from . import SKILL_MAP

__author__ = "josh"

LINEUP_SLOTS = [
    "cf",
    "ss",
    "2b",
    "1b",
    "lf",
    "3b",
    "rf",
    "c",
    "p",
]

class Team(object):
    """A Baseball Team class."""

    def __init__(self, city, mascot):
        # self.players = self.load_team()
        self.city = city
        self.mascot = mascot

        self.batter_index = 0  # index on the lineup
        self.current_pitcher_index = 0  # index on the roster (players)
        self.stats = stats.TeamStats()
        self.players = []

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

    def set_lineup(self, style="auto"):
        """
        Set the lineup and validate it.
        """
        styles = [
            "auto",
            "defensive",
            "offensive",
            "prioritized",
        ]
        if style not in styles:
            raise ValueError("Setting lineup with invalid style: " + style)
        if style == "auto":
            self.auto_set_lineup()
        elif style == "defensive":
            self.select_defensive_lineup()
        elif style == "offensive":
            self.select_offensive_lineup()
        elif style == "prioritized":
            self.select_offensive_lineup(prioritized_positions=True)

        if len(self.lineup) != 9:
            raise ValueError("Lineup must have exactly 9 players")

        if validate_lineup_slots(self.lineup):
            # debug
            #print("Lineup looks good")
            pass

    def auto_set_lineup(self):
        """
        This will automatically set the lineup using the first 9 
        players in the csv file and setting their positions in a
        fixed order. It will skip over starting pitchers for 
        position players in the batting order.
        """
        hitters = [p for p in self.players if p.position != 'sp']
        hitters = hitters[:9]

        positions = ['cf','ss','1b','lf','rf','2b','3b','c','p']

        self.lineup = [
            LineupSlot(player, pos)
            for player, pos in zip(hitters, positions)
        ]

    def position_score(self, player, position):
        return player.ratings.get(position, 0)

    def select_defensive_lineup(self):
        """
        This will automatically put together a defensive lineup, but
        it will greedily pick the best player aavailable at each
        position, in the order of priority set in the LINEUP_SLOTS.
        """
        lineup = {}
        self.lineup = []
        used_players = set()
        for player in self.players:
            player.rate_player()

        for position in LINEUP_SLOTS:
            candidates = [
                p for p in self.players
                if p not in used_players and position in p.ratings
            ]

            best = max(
                candidates,
                key=lambda p: self.position_score(p, position),
                default=None
            )

            if best:
                self.lineup.append(LineupSlot(best, position))
                lineup[position] = best
                used_players.add(best)

    def select_offensive_lineup(self, prioritized_positions=False):
        """
        Create an offensive lineup.
        This won't properly assign the players to positions.
        """
        lineup = {}
        self.lineup = []
        used_players = set()
        for player in self.players:
            player.rate_player()
        self.set_hitters()
        leadoff = max(self.hitters, key=lambda p: self.profiles[p]["on_base"] + self.profiles[p]["speed"])
        #print("leadoff set to " + leadoff.name)
        remaining = [p for p in self.hitters if p != leadoff]
        two_hitter = max(remaining, key=lambda p: self.profiles[p]["on_base"])
        remaining.remove(two_hitter)
        three_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(three_hitter)
        cleanup = max(remaining, key=lambda p: self.profiles[p]["power"] + self.profiles[p]["contact"])
        remaining.remove(cleanup)
        five_hitter = max(remaining, key=lambda p: self.profiles[p]["power"])
        remaining.remove(five_hitter)
        six_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(six_hitter)
        seven_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(seven_hitter)
        eight_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(eight_hitter)
        nine_hitter = max(remaining, key=lambda p: self.profiles[p]["speed"] + self.profiles[p]["on_base"])
        self.lineup = [
            leadoff,
            two_hitter,
            three_hitter,
            cleanup,
            five_hitter,
            six_hitter,
            seven_hitter,
            eight_hitter,
            nine_hitter,
        ]
        if prioritized_positions:
            self.assign_priority_positions()
        else:
            self.assign_positions()

    
    def assign_positions(self):
        """
        Greedily assign defensive positions to the 9 hitters.
        One player will become DH.
        Batting order must not change.
        """
        remaining_players = set(self.lineup)
        remaining_positions = set(LINEUP_SLOTS) - {"p"}  # ignore pitcher
        assignments = {}  # player -> position

        # Greedy assignment of positions
        while remaining_players and remaining_positions:
            best = None  # (skill, player, position)

            for player in remaining_players:
                for pos in remaining_positions:
                    skill = player.ratings.get(pos, 0)

                    if best is None or skill > best[0]:
                        best = (skill, player, pos)

            _, player, position = best
            assignments[player] = position

            remaining_players.remove(player)
            remaining_positions.remove(position)

        # Whoever is left becomes DH
        for player in remaining_players:
            assignments[player] = "dh"

        # Rebuild lineup IN ORIGINAL BATTING ORDER
        self.lineup = [
            LineupSlot(player, assignments[player])
            for player in self.lineup
        ]

    def assign_priority_positions(self):
        """
        Assign defensive positions without changing batting order.
        Uses position priority, then best available player for each position.
        """
        position_priority = ["ss", "cf", "2b", "c", "3b", "rf", "1b", "lf"]

        remaining_players = set(self.lineup)
        assignments = {}  # player -> position

        # Assign positions by priority
        for pos in position_priority:
            if not remaining_players:
                break

            # Pick best player remaining for this position
            best_player = max(
                remaining_players,
                key=lambda p: p.ratings.get(pos, 0)
            )

            assignments[best_player] = pos
            remaining_players.remove(best_player)

        # Whoever is left becomes DH
        for player in remaining_players:
            assignments[player] = "dh"

        # Rebuild lineup IN ORIGINAL BATTING ORDER
        self.lineup = [
            LineupSlot(player, assignments[player])
            for player in self.lineup
        ]


    def current_batter(self):
        return self.lineup[self.batter_index]

    def next_batter(self):
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter()

    def current_pitcher(self):
        return self.players[self.current_pitcher_index]

    def display_lineup(self):
        for slot in self.lineup:
            print(f"{slot.position:<2}" + "  " + slot.horizontal())

    def set_hitters(self):
        self.hitters = [p for p in self.players if p.position not in ("sp", "rp")]
        self.profiles = {p: offensive_profile(p) for p in self.hitters}
        # for profile in self.profiles:
        #     print(profile)
        for p in self.players:
            p.profile = offensive_profile(p)
        # for p in self.players:
        #     print(p.offensive_profile)

class LineupSlot(object):
    def __init__(self, player, position):
        self.player = player      # Player object
        self.position = position  # '1B', 'CF', 'SP', etc.

    def __getattr__(self, name):
        # Forward unknown attributes to Player
        return getattr(self.player, name)


def offensive_profile(player):
    s = player.skills
    return {
        "on_base": 0.5 * s["contact"] + 0.4 * s["eye"] + 0.1 * s["clutch"],
        "power": s["power"],
        "speed": 0.6 * s["speed"] + 0.4 * s["base_running"],
        "bat_control": 0.7 * s["contact"] + 0.3 * s["bunting"],
        "contact": s["contact"],
        "overall": (
            0.35 * s["contact"] +
            0.30 * s["power"] +
            0.20 * s["eye"] +
            0.10 * s["speed"] +
            0.05 * s["clutch"]
        )
    }

def validate_lineup_slots(lineup):
    required = set(LINEUP_SLOTS) - {"p"}  # ignore pitcher
    used = []

    for slot in lineup:
        pos = slot.position.lower()
        if pos != "p":   # allow DH/etc
            used.append(pos)

    used_set = set(used)

    # check for duplicates
    if len(used) != len(used_set):
        duplicates = [p for p in used if used.count(p) > 1]
        raise ValueError(f"Duplicate lineup positions: {set(duplicates)}")

    # check for missing positions
    missing = required - used_set
    if missing:
        raise ValueError(f"Missing lineup positions: {missing}")

    return True
