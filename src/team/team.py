"""The team class.

Basically, a city, a mascot and a list of players.

"""

import csv
import copy
import logging

# from src.stats import stats
from src.player.player import Player
from src.player.player_formatters import PlayerTableFormatter
from src.player.skill_map import SKILL_MAP

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
]


class Team(object):
    """A Baseball Team class."""

    def __init__(self, city=None, mascot=None):
        """Initialize the team."""
        self.city = city
        self.mascot = mascot
        self.lineup = None
        self.pitcher = None
        self.batter_index = 0  # index on the lineup
        self.players = []
        self.logger = logging.getLogger("details")

    def load_team(self, path=None, rows=None):
        """Load a team from a csv file."""
        if rows is None:
            rows = []
        self.team_file = path
        self.players: list[Player] = []
        
        if path:
            with open(path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                for row in reader:
                    self._add_player(row)

        for row in rows:
            self._add_player(row)

    def _add_player(self, row):
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
        try:
            player.id = row["ID"]
        except:
            pass
        self.players.append(player)

    def set_lineup(self, style="auto", dh=True):
        """
        Set the lineup and validate it.
        """
        for player in self.players:
            player.rate_player()
        styles = [
            "auto",
            "defensive",
            "offensive",
            "prioritized",
        ]
        if style not in styles:
            raise ValueError("Setting lineup with invalid style: " + style)
        if style == "auto":
            self.auto_set_lineup(dh)
        elif style == "defensive":
            self.select_defensive_lineup(dh)
        elif style == "offensive":
            self.select_offensive_lineup(dh)
        elif style == "prioritized":
            self.select_offensive_lineup(dh, prioritized_positions=True)

        if len(self.lineup) != 9:
            self.logger.error("Lineup has {} members".format(len(self.lineup)))
            raise ValueError("Lineup must have exactly 9 players")

        if validate_lineup_slots(self.lineup, self.pitcher, dh):
            self.logger.debug("Lineup looks good")

    def auto_set_lineup(self, dh):
        """
        This will automatically set the lineup using the first 8 or 9
        players in the csv file and setting their positions in a
        fixed order. It will skip over starting pitchers for
        position players in the batting order.
        """
        hitters = [p for p in self.players if p.position != "sp"]
        if dh:
            hitters = hitters[:9]
        else:
            hitters = hitters[:8]

        positions = ["cf", "ss", "1b", "lf", "rf", "2b", "3b", "c"]
        if dh:
            positions.append("dh")

        self.lineup = [
            LineupSlot(player, pos) for player, pos in zip(hitters, positions)
        ]
        self.set_pitcher(dh)

    def set_pitcher(self, dh):
        """
        Docstring for set_pitcher

        :param dh: A boolean that tells whether to add the pitcher to
        the batting lineup or not. If dh is true, the pitcher doesn't
        need to bat.
        """
        best: int = 0
        pitcher = None
        for player in self.players:
            if player.ratings["p"] > best:
                pitcher = player
                best = player.ratings["p"]
        self.pitcher = pitcher
        if not dh:
            self.lineup.append(LineupSlot(pitcher, "p"))

    def position_score(self, player, position):
        """Return the position score for a player."""
        return player.ratings.get(position, 0)

    def select_defensive_lineup(self, dh):
        """
        This will automatically put together a defensive lineup, but
        it will greedily pick the best player aavailable at each
        position, in the order of priority set in the LINEUP_SLOTS.
        """
        lineup: dict[str, Player] = {}
        self.lineup = []
        used_players = set()

        self.set_hitters()
        if dh:
            dh_batter = max(self.hitters, key=lambda p: self.profiles[p]["overall"])
            self.lineup.append(LineupSlot(dh_batter, "dh"))
            used_players.add(dh_batter)

        slots = copy.deepcopy(LINEUP_SLOTS)
        if dh:
            slots.append("dh")

        for position in slots:
            candidates: list[Player] = [
                p
                for p in self.players
                if p not in used_players and position in p.ratings
            ]

            best = max(
                candidates, key=lambda p: self.position_score(p, position), default=None
            )

            if best:
                self.lineup.append(LineupSlot(best, position))
                lineup[position] = best
                used_players.add(best)

        self.set_pitcher(dh)

    def select_offensive_lineup(self, dh, prioritized_positions=False):
        """
        Create an offensive lineup.
        This does not assign the players to positions.
        We call another function at the end to do that.
        """
        self.lineup = []
        self.set_hitters()
        leadoff = max(
            self.hitters,
            key=lambda p: self.profiles[p]["on_base"] + self.profiles[p]["speed"],
        )
        remaining = [p for p in self.hitters if p != leadoff]
        two_hitter = max(remaining, key=lambda p: self.profiles[p]["on_base"])
        remaining.remove(two_hitter)
        three_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(three_hitter)
        cleanup = max(
            remaining,
            key=lambda p: self.profiles[p]["power"] + self.profiles[p]["contact"],
        )
        remaining.remove(cleanup)
        five_hitter = max(remaining, key=lambda p: self.profiles[p]["power"])
        remaining.remove(five_hitter)
        six_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(six_hitter)
        seven_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(seven_hitter)
        eight_hitter = max(remaining, key=lambda p: self.profiles[p]["overall"])
        remaining.remove(eight_hitter)
        self.set_pitcher(dh)
        if dh:
            nine_hitter = max(
                remaining,
                key=lambda p: self.profiles[p]["speed"] + self.profiles[p]["on_base"],
            )
        else:
            nine_hitter = self.pitcher
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
            self.assign_priority_positions(dh)
        else:
            self.assign_positions(dh)

    def assign_positions(self, dh):
        """
        Greedily assign defensive positions to the 8 or 9 hitters.
        One player will become DH if dh is True
        If dh is false, we need to set the pitcher.
        Batting order must not change.
        """
        remaining_players = set(self.lineup)
        slots = copy.deepcopy(LINEUP_SLOTS)
        if dh:
            slots.append("dh")
        else:
            slots.append("p")
        remaining_positions = set(slots)
        assignments: dict[Player, str] = {}  # player -> position

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
            LineupSlot(player, assignments[player]) for player in self.lineup
        ]

    def assign_priority_positions(self, dh):
        """
        Assign defensive positions without changing batting order.
        Uses position priority, then best available player for each position.
        """
        position_priority = ["ss", "cf", "2b", "c", "3b", "rf", "1b", "lf"]
        if not dh:
            position_priority = ["p"] + position_priority
        remaining_players = set(self.lineup)
        assignments: dict[Player, str] = {}  # player -> position

        # Assign positions by priority
        for pos in position_priority:
            if not remaining_players:
                break

            # Pick best player remaining for this position
            best_player = max(remaining_players, key=lambda p: p.ratings.get(pos, 0))

            assignments[best_player] = pos
            remaining_players.remove(best_player)

        if dh:
            # Whoever is left becomes DH
            for player in remaining_players:
                assignments[player] = "dh"

        # Rebuild lineup IN ORIGINAL BATTING ORDER
        self.lineup = [
            LineupSlot(player, assignments[player]) for player in self.lineup
        ]

    def current_batter(self):
        """Return the current batter."""
        return self.lineup[self.batter_index]

    def next_batter(self):
        """Increment the batter index and return the next batter."""
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter()

    def current_pitcher(self):
        """Return the current pitcher."""
        return self.pitcher

    def display_lineup(self):
        """Display the lineup."""
        if self.city or self.mascot:
            self.logger.info("{} {}".format(self.city, self.mascot))
        for slot in self.lineup:
            self.logger.info(
                f"{slot.position:<2}" + "  " + PlayerTableFormatter.horizontal(slot)
            )
        self.display_pitcher()

    def display_pitcher(self):
        """Display the pitcher."""
        pitcher_hitting = False
        if self.pitcher:
            for slot in self.lineup:
                if slot.position == "p":
                    pitcher_hitting = True
            if not pitcher_hitting:
                self.logger.info("Starting Pitcher")
                self.logger.info(f"p   {PlayerTableFormatter.horizontal(self.pitcher)}")

    def set_hitters(self):
        """Set the hitters."""
        self.hitters = [p for p in self.players if p.position not in ("sp", "rp")]
        self.profiles = {p: offensive_profile(p) for p in self.hitters}
        for p in self.players:
            p.profile = offensive_profile(p)


class LineupSlot(object):
    def __init__(self, player, position):
        """Initialize the lineup slot."""
        self.player = player  # Player object
        self.position = position  # '1B', 'CF', 'SP', etc.

    def __getattr__(self, name):
        """Forward unknown attributes to Player."""
        return getattr(self.player, name)


def offensive_profile(player):
    """Return the offensive profile for a player."""
    s = player.skills
    return {
        "on_base": 0.5 * s["contact"] + 0.4 * s["eye"] + 0.1 * s["clutch"],
        "power": s["power"],
        "speed": 0.6 * s["speed"] + 0.4 * s["base_running"],
        "bat_control": 0.7 * s["contact"] + 0.3 * s["bunting"],
        "contact": s["contact"],
        "overall": (
            0.35 * s["contact"]
            + 0.30 * s["power"]
            + 0.20 * s["eye"]
            + 0.10 * s["speed"]
            + 0.05 * s["clutch"]
        ),
    }


def validate_lineup_slots(lineup, pitcher, dh):
    """Validate the lineup slots."""
    required = set(LINEUP_SLOTS)
    used: list[str] = []

    for slot in lineup:
        pos = slot.position.lower()
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

    if dh:
        if "dh" not in used:
            raise ValueError(f"Missing lineup positions: {'dh'}")
    else:
        if "p" not in used:
            raise ValueError(f"Missing lineup positions: {'p'}")
    if pitcher is None:
        raise ValueError("Pitcher is not set.")

    return True
