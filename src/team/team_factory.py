"""
The TeamFactory class.

PlayerFactory.create()      → always age 17, base skills
TeamFactory.generate_team() → creates N players, ages each one to a
                              realistic roster age, checks distribution
"""

import csv
import dataclasses
import random
from scipy.stats import skewnorm
import uuid

from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.player.player_factory import PlayerFactory
from src.player.player_record import PlayerRecord
from src.player.talent_caps import generate_talent_caps
from src.team.team_record import TeamRecord

__author__ = "josh"
_MIN_AGE = 18
_MAX_AGE = 44
_MEAN_AGE = 24
_STD_DEV = 6.0
_SKEW = 0.2


class TeamFactory:
    def __init__(
        self, conn=None, rng=None, id_factory=None, log_level: int | None = None
    ):
        self.conn = conn
        if conn is not None:
            self.cap_repo = TalentCapRepository(conn)
        else:
            self.cap_repo = None
        self.player_factory = PlayerFactory(conn=conn, rng=rng, log_level=log_level)
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self.rng = rng or random.Random()

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

    def generate_team(self, *, city: str, mascot: str, size: int = 160) -> TeamRecord:
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
            size: Number of players on roster (default: 160)

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
                    age = self._draw_roster_age(players)
                    players.append(self._create_aged_player(age, position=position))

            # Fill remaining slots with random positions
            remaining = size - len(players)
            for _ in range(remaining):
                age = self._draw_roster_age(players)
                players.append(self._create_aged_player(age))

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
                    age = self._draw_roster_age(players)
                    players.append(self._create_aged_player(age, position=position))

            # Fill remaining slots
            remaining = size - len(players)
            for _ in range(remaining):
                age = self._draw_roster_age(players)
                players.append(self._create_aged_player(age))

        return TeamRecord(
            id=uuid.uuid4().hex,
            city=city,
            mascot=mascot,
            players=tuple(players),
        )

    def _create_aged_player(
        self, age: int, position: str | None = None
    ) -> PlayerRecord:
        """
        Create an appropriately aged player for this team
        """
        player = self.player_factory.create(position=position)
        caps = generate_talent_caps(player.skills.as_dict(), rng=self.rng)
        aged_skills = player.skills.age_to(age, rng=self.rng, caps=caps)
        if self.cap_repo is not None:
            self.cap_repo.insert(player.id, caps)
        return dataclasses.replace(player, skills=aged_skills)

    def _draw_roster_age(self, current_players: list[PlayerRecord]) -> int:
        """
        Draw a single realistic roster age using a right-skewed normal
        distribution, rerolling if hard roster constraints are violated.
        """

        current_ages = [p.age for p in current_players]

        for _ in range(10_000):
            # Derive a seed from self.rng so scipy's RNG is reproducible
            # when this factory is seeded (e.g. in tests or simulations)
            seed = self.rng.getrandbits(32)
            age = int(
                round(
                    skewnorm.rvs(
                        a=_SKEW,
                        loc=_MEAN_AGE,
                        scale=_STD_DEV,
                        random_state=seed,
                    )
                )
            )

            # Implement the roster constraints
            if age < _MIN_AGE or age > _MAX_AGE:
                continue
            if age < 21 and sum(1 for a in current_ages if a < 21) >= 2:
                continue
            if age > 38 and sum(1 for a in current_ages if a > 38) >= 3:
                continue
            if age >= 40 and sum(1 for a in current_ages if a >= 40) >= 1:
                continue

            return age

        return _MEAN_AGE  # fallback if constraints can't be satisfied
