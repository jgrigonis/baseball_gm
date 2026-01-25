# tests/team/test_team_in_game_factory.py
from src.team.team_in_game_factory import TeamInGameFactory
from src.player.player_in_game import PlayerInGame
from tests.factories.team_record_factory import make_team_record
from tests.factories.player_record_factory import make_player_record
from src.player.player_evaluator import EXPECTED_RATINGS


def test_team_in_game_from_record_creates_players():
    """TeamInGameFactory.from_record builds PlayerInGame objects from the TeamRecord"""
    record = make_team_record(size=9)  # 9 canonical PlayerRecords

    team_in_game = TeamInGameFactory.from_record(record)

    # TeamInGame keeps a reference to the original TeamRecord
    assert team_in_game.record is record

    # TeamInGame has the correct number of in-game players
    assert len(team_in_game.players) == 9

    # Each in-game player wraps a PlayerRecord from the team
    for p in team_in_game.players:
        assert isinstance(p, PlayerInGame)
        assert p.record in record.players


def test_player_ratings_have_all_expected():
    record = make_player_record()  # PlayerRecord with skills
    p = PlayerInGame.from_record(record)

    # Every rating category exists
    assert set(p.ratings.keys()) == EXPECTED_RATINGS


def test_team_in_game_players_are_independent_from_record():
    """Mutating in-game players does not mutate the underlying records"""
    record = make_team_record(size=25)

    team_in_game = TeamInGameFactory.from_record(record)
    p_ingame = team_in_game.players[0]

    # Change ratings in-game
    original = p_ingame.ratings.copy()
    print(p_ingame.skills)
    for k in p_ingame.ratings:
        p_ingame.ratings[k] += 10

    # Original PlayerRecord skills must remain unchanged
    for k, v in p_ingame.record.skills.items():
        assert (
            v == original[k] - 10 if k in original else v
        )  # unchanged canonical skills
