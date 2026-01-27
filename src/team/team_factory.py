"""The TeamFactory class."""

import csv
import uuid

from src.player.player_factory import PlayerFactory
from src.player.player_record import PlayerRecord
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

    def generate_team(self, *, city: str, mascot: str, size=40) -> TeamRecord:
        # if size < 9:
        #     raise ValueError("Team must have at least 9 players")
        # If the size of the team is over 26, there should be:
        # 7 starting pitchers, 6 rp
        # 2 c, 1 ss, 1 2b, 1 3b, 1 1b, 1 lf, 1 cf, 1 rf, 2 if, 2 of
        # rest random
        players = tuple(self.player_factory.create() for _ in range(size))
        return TeamRecord(
            id=uuid.uuid4().hex,
            city=city,
            mascot=mascot,
            players=players,
        )
