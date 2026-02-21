"""
The TeamFactory class.

PlayerFactory.create()      → always age 17, base skills
TeamFactory.generate_team() → creates N players, ages each one to a
                              realistic roster age, checks distribution
"""

import csv
import uuid

from src.player.player_factory import PlayerFactory
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.team.team_record import TeamRecord

__author__ = "josh"


class TeamFactory:
    def __init__(self, rng=None, id_factory=None, log_level: int | None = None):
        self.player_factory = PlayerFactory(rng, log_level=log_level)
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)

    def from_csv(self, path: str, *, city: str, mascot: str) -> TeamRecord:
        players: list[PlayerRecord] = []

        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader, start=1):
                try:
                    players.append(PlayerRecord.from_csv_row(row))
                except Exception as e:
                    raise ValueError(f"Invalid player row {i} in {path}: {row}") from e
        if len(players) < 9:
            raise ValueError("Team must have at least 9 players")
        return TeamRecord(
            id=uuid.uuid4().hex,
            city=city,
            mascot=mascot,
            players=tuple(players),
        )

    def generate_team(self, *, city: str, mascot: str, size: int = 40) -> TeamRecord:
        """
        Generate a team with realistic positional distribution.

        For teams of 26+ players:
        - 7 starting pitchers (sp)
        - 6 relief pitchers (rp)
        - 2 catchers (c)
        - 1 of each infield position (ss, 2b, 3b, 1b)
        - 1 of each outfield position (lf, cf, rf)
        - 2 utility infielders (if)
        - 2 utility outfielders (of)
        - Remaining slots: random positions

        For smaller teams, scales down proportionally while maintaining balance.

        Args:
            city: Team city name
            mascot: Team mascot name
            size: Number of players on roster (default: 40)

        Returns:
            TeamRecord with generated players

        Raises:
            ValueError: If size < 9 (minimum for fielding a team)
        """
        if size < 9:
            raise ValueError("Team must have at least 9 players")

        players = []

        if size >= 26:
            # Full roster with specified distribution
            position_counts = {
                "sp": 7,
                "rp": 6,
                "c": 2,
                "ss": 1,
                "2b": 1,
                "3b": 1,
                "1b": 1,
                "lf": 1,
                "cf": 1,
                "rf": 1,
                "if": 2,
                "of": 2,
            }

            # Generate players for each position
            for position, count in position_counts.items():
                for _ in range(count):
                    players.append(self.player_factory.create(position=position))

            # Fill remaining slots with random positions
            remaining = size - len(players)
            for _ in range(remaining):
                players.append(self.player_factory.create())

        else:
            # Smaller roster - use proportional distribution
            # Calculate how many slots for each position type
            pitchers_needed = max(1, size // 5)  # ~20% pitchers minimum

            # Distribute pitchers
            if pitchers_needed == 1:
                # Minimum: just 1 pitcher (use SP)
                core_positions = {"sp": 1}
            elif pitchers_needed == 2:
                # Small roster: 1 SP, 1 RP
                core_positions = {"sp": 1, "rp": 1}
            else:
                # Split between starters and relievers
                sp_count = max(1, pitchers_needed * 2 // 3)
                rp_count = max(1, pitchers_needed - sp_count)
                core_positions = {"sp": sp_count, "rp": rp_count}

            # Add required defensive positions (8 positions)
            core_positions.update(
                {
                    "c": 1,
                    "ss": 1,
                    "2b": 1,
                    "3b": 1,
                    "1b": 1,
                    "lf": 1,
                    "cf": 1,
                    "rf": 1,
                }
            )

            # Generate core positions
            for position, count in core_positions.items():
                for _ in range(count):
                    players.append(self.player_factory.create(position=position))

            # Fill remaining slots
            remaining = size - len(players)
            for _ in range(remaining):
                players.append(self.player_factory.create())

        return TeamRecord(
            id=uuid.uuid4().hex,
            city=city,
            mascot=mascot,
            players=tuple(players),
        )

    def _create_aged_player(self, position: str | None = None) -> PlayerRecord:
        player = self.player_factory.create(position=position)
        age = self._draw_roster_age()
        return PlayerSkills.age_to(player, age)
