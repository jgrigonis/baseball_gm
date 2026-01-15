# tests/factories/team_record_factory.py
import itertools
from src.team.team_record import TeamRecord
from tests.factories.player_record_factory import make_player_record

_counter = itertools.count()


def make_team_record(
    *,
    id: str | None = None,
    city="Testville",
    mascot="Tests",
    size=26,
    players=None,
):
    n = next(_counter)

    if players is None:
        players = [make_player_record() for _ in range(size)]

    return TeamRecord(
        id=id or f"team-{n}",
        city=city,
        mascot=mascot,
        players=tuple(players),
    )
