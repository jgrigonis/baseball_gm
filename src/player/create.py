import random
import uuid

import src.game.game_exceptions as game_exceptions
from src.player import positions
from src.player.player import Player
from src.name_generator.names import NameGenerator


def create(pos=None):
    id = uuid.uuid4().hex
    ng = NameGenerator()
    my_player = Player(ng.first("male"), ng.last(), position=pos, id=id)
    my_player.generate()
    return my_player


def create_players(position=None, num=1):
    players = []
    for _ in range(num):
        if position is None:
            pos = random.choice(positions)
        elif isinstance(position, list):
            pos = random.choice(position)
        else:
            pos = position
        if pos not in positions:
            raise game_exceptions.BadPositionException()
        players.append(create(pos))
    return players
