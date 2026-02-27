# tests/factories/player_record_factory.py
import itertools
import random

from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import AFFINITY_POSITIONS  # Changed from POSITIONS
import src.game.game_exceptions as game_exceptions

_counter = itertools.count()


def _resolve_position(rng, position: str | None) -> str:
    if position is None:
        return rng.choice(AFFINITY_POSITIONS)  # Changed
    if position not in AFFINITY_POSITIONS:  # Changed
        raise game_exceptions.BadPositionException()
    return position


def make_player_record(
    *,
    id: str | None = None,
    first_name="Test",
    last_name=None,
    bats="R",
    throws="R",
    position=None,
    skills: dict | None = None,
    rng=None,
):
    n = next(_counter)
    rng = rng or random.Random()
    position = _resolve_position(rng, position)
    if skills is None:
        skills = PlayerSkills.generate(rng, position, throws)

    return PlayerRecord(
        id=id or f"player-{n}",
        first_name=first_name,
        last_name=last_name or f"Player{n}",
        bats=bats,
        throws=throws,
        position=position,
        skills=skills,
    )


# # tests/factories/player_record_factory.py
# import itertools
# import random

# from src.player.player_record import PlayerRecord
# from src.player.player_skills import PlayerSkills
# from src.player.positions import POSITIONS
# import src.game.game_exceptions as game_exceptions


# _counter = itertools.count()


# def _resolve_position(rng, position: str | None) -> str:
#     if position is None:
#         return rng.choice(POSITIONS)
#     if position not in POSITIONS:
#         raise game_exceptions.BadPositionException()
#     return position


# def make_player_record(
#     *,
#     id: str | None = None,
#     first_name="Test",
#     last_name=None,
#     bats="R",
#     throws="R",
#     position=None,
#     skills: dict | None = None,
#     rng=None,
# ):
#     n = next(_counter)
#     rng = rng or random.Random()
#     position = _resolve_position(rng, position)
#     if skills is None:
#         skills = PlayerSkills.generate(rng, position, throws)

#     return PlayerRecord(
#         id=id or f"player-{n}",
#         first_name=first_name,
#         last_name=last_name or f"Player{n}",
#         bats=bats,
#         throws=throws,
#         position=position,
#         skills=skills,
#     )
