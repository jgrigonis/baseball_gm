# tests/api/test_lobby_team_entries.py
from src.api.services import lobby_teams
from src.league import divisions


def test_thirty_is_the_world_league():
    cities = {t["city"] for t in lobby_teams.team_entries("L1", 30)}
    assert cities == divisions.world_cities()


def test_thirty_two_adds_two_of_the_extra_teams():
    entries = lobby_teams.team_entries("L1", 32)
    assert len({t["city"] for t in entries}) == 32
    extras = {t["city"] for t in entries} - divisions.world_cities()
    assert len(extras) == 2
    assert extras <= {"Berlin", "Seattle", "Portland"}
    assert entries == lobby_teams.team_entries("L1", 32)


def test_every_extra_team_turns_up_in_some_league():
    seen = set()
    for i in range(30):
        seen |= {t["city"] for t in lobby_teams.team_entries(f"L{i}", 32)}
    assert {"Berlin", "Seattle", "Portland"} <= seen


def test_smaller_leagues_pick_the_same_teams_every_time():
    first = lobby_teams.team_entries("L1", 20)
    assert len(first) == 20
    assert first == lobby_teams.team_entries("L1", 20)
    assert {t["city"] for t in first} <= divisions.world_cities()
