# tests/league/test_real_seasons.py
"""A real season's data file and how its clubs become a league's teams."""

import random

from src.league import real_seasons, team_pool
from src.player.positions import SKILLS


def test_2025_is_available():
    assert 2025 in real_seasons.available()


def test_the_2025_file_has_every_club_with_40_rated_players():
    clubs = real_seasons.load(2025)["clubs"]
    assert len(clubs) == real_seasons.TEAMS
    assert set(real_seasons.SKILLS) == set(SKILLS)
    for club in clubs:
        assert len(club["players"]) == 40
        pitchers = [p for p in club["players"] if p["pos"] in ("sp", "rp")]
        assert 13 <= len(pitchers) <= 27
        for p in club["players"]:
            assert len(p["skills"]) == len(real_seasons.SKILLS)
            assert all(1 <= v <= 100 for v in p["skills"])
            assert 18 <= p["age"] <= 45


def _league_teams(n=30):
    return [t.key for t in team_pool.draw(n, random.Random(4))]


def test_clubs_go_to_teams_in_their_city_first():
    teams = [("Boston", "Beacons"), ("New York", "Titans"), *_league_teams()]
    teams = list(dict.fromkeys(teams))[:30]
    clubs = real_seasons.assign_clubs(real_seasons.load(2025)["clubs"], teams)
    by_team = {t: c["name"] for t, c in zip(teams, clubs)}
    assert by_team[("Boston", "Beacons")] == "Boston Red Sox"
    # Two New York clubs: the bigger crowd gets the city's team.
    assert by_team[("New York", "Titans")] == "New York Yankees"
    assert len({c["id"] for c in clubs}) == 30


def test_the_rest_go_biggest_crowds_to_biggest_markets():
    teams = _league_teams()
    clubs = real_seasons.assign_clubs(real_seasons.load(2025)["clubs"], teams)
    unmatched = [
        (team_pool.get(*t).market, c["attendance"])
        for t, c in zip(teams, clubs)
        if not c["name"].startswith(t[0] + " ")
    ]
    unmatched.sort(key=lambda x: -x[1])
    markets = [m for m, _ in unmatched]
    assert markets == sorted(markets, reverse=True)


def test_build_teams_gives_real_players_their_ages_and_skills():
    teams = _league_teams()
    built = real_seasons.build_teams(2025, teams, random.Random(1))
    assert [(t.city, t.mascot) for t in built] == teams
    players = [p for t in built for p in t.players]
    assert len(players) == 30 * 40
    assert len({p.id for p in players}) == len(players)
    judge = next(p for p in players if p.last_name == "Judge")
    assert judge.first_name == "Aaron"
    assert judge.skills.age == 33
    assert judge.skills["power"] >= 90
