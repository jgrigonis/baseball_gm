# tests/league/test_real_players.py
"""Every real player-season custom teams pick from."""

import random

from src.league.real_seasons import SKILLS, players


def test_the_file_covers_every_era():
    assert players.count() > 70_000
    first, *_ = players.search("addy 1871")[0]
    assert first.year == 1871


def test_a_season_has_all_skills_in_range():
    griffey = players.get("griffke02-1997")
    assert griffey.name == "Ken Griffey"
    assert griffey.age == 27 and griffey.born == 1969
    assert griffey.pos == "cf" and griffey.teams == ("SEA",)
    assert set(griffey.skills) == set(SKILLS)
    assert all(1 <= v <= 100 for v in griffey.skills.values())
    assert griffey.skills["power"] >= 90


def test_search_by_name_parts_and_year():
    found, total = players.search("ken grif 1997")
    assert [s.key for s in found] == ["griffke02-1997"]
    assert total == 1
    found, total = players.search("griffey")
    assert total == len(found) > 20
    # Senior's seasons before Junior's, each in year order.
    born = [s.born for s in found]
    assert born == sorted(born)


def test_search_ignores_accents_and_caps():
    found, _ = players.search("PENA")
    assert any("ñ" in s.last for s in found)


def test_search_limits_but_counts_everything():
    found, total = players.search("smith", limit=10)
    assert len(found) == 10 and total > 100
    assert players.search("") == ([], 0)


def test_two_way_players_keep_their_pitching():
    ohtani = players.get("ohtansh01-2023")
    assert ohtani.pos == "dh"
    assert ohtani.skills["strikes"] >= 70


def test_a_season_becomes_a_game_player():
    ford = players.get("fordwh01-1961").record(random.Random(1))
    assert (ford.first_name, ford.last_name, ford.throws) == ("Whitey", "Ford", "L")
    assert ford.position == "sp"
    assert ford.skills.age == 32
