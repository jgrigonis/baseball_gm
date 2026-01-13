# tests/factories/player_in_game_factory.py
from src.player.player_in_game import PlayerInGame
from tests.factories.player_record_factory import make_player_record

def make_player_in_game(
    *,
    id: str,
    ratings: dict,
):
    record = make_player_record(id=id)
    p = PlayerInGame(record)
    p.ratings = ratings.copy()  # ensure immutability tests pass
    return p
