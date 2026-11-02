# tests/api/web/test_player_compare.py
"""The player panel compares up to three players side by side, tagging each
"You get" / "You give" when it's opened from a trade offer."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user, get_gm_or_viewer
from src.api.main import app


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season(year=2025)
    team = factory.team(city="My", mascot="Team")
    factory.league_season(league, season)
    factory.league_season_team(league, season, team)
    factory.gm(team=team, league=league, is_ai=False)
    other = factory.team(city="Other", mascot="Club")
    factory.league_season_team(league, season, other)
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
                              completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 0)""",
        (factory._id(), season.id, team.id, other.id),
    )
    players = [
        factory.rated_player(team, league, 55, name=n)
        for n in ("Able", "Baker", "Cole", "Dunn")
    ]
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": None, "team_id": None}
    yield TestClient(app), league, players
    app.dependency_overrides.clear()


def _panel(client, league, first, *compare, **sides):
    q = [("compare", p.id) for p in compare]
    q += [(side, p.id) for side, ps in sides.items() for p in ps]
    return client.get(f"/leagues/{league.id}/players/{first.id}/panel", params=q).text


def test_one_player_offers_compare(setup):
    client, league, (a, *_) = setup
    html = _panel(client, league, a)
    assert "Player Detail" in html
    assert "Compare ↔" in html
    assert "pp-slot-remove" not in html


def test_two_players_can_add_a_third(setup):
    client, league, (a, b, *_) = setup
    html = _panel(client, league, a, b)
    assert 'class="player-panel split"' in html
    assert "Player Comparison · 2 of 3" in html
    assert html.count('class="pp-slot-remove"') == 2
    assert "+ Add player" in html
    assert "Remove a player to add another" not in html


def test_three_players_side_by_side_and_no_more(setup):
    client, league, (a, b, c, d) = setup
    html = _panel(client, league, a, b, c, d)
    assert 'class="player-panel split split3"' in html
    assert "Player Comparison · 3 of 3" in html
    for p in (a, b, c):
        assert f'data-player-id="{p.id}" data-side=""' in html
    assert d.id not in html
    assert "Remove a player to add another" in html


def test_the_same_player_twice_shows_once(setup):
    client, league, (a, b, *_) = setup
    html = _panel(client, league, a, a, b)
    assert "Player Comparison · 2 of 3" in html


def test_players_from_a_trade_are_tagged(setup):
    client, league, (a, b, c, _) = setup
    html = _panel(client, league, a, b, c, get=[a, b], give=[c])
    assert html.count('<span class="pp-side get">You get</span>') == 2
    assert html.count('<span class="pp-side give">You give</span>') == 1
    assert f'data-player-id="{c.id}" data-side="give"' in html


def _off_role(html):
    """The section titles inside each player's collapsed off-role toggle."""
    import re

    return [
        re.findall(r'pd-section-title">(\w+)<', block)
        for block in re.findall(r'<details class="pd-offrole".*?</details>', html, re.S)
    ]


def test_hitter_tucks_pitching_behind_a_toggle(setup):
    client, league, (a, *_) = setup
    html = _panel(client, league, a)
    assert _off_role(html) == [["Pitching"]]
    assert '<details class="pd-offrole" ontoggle' in html
    assert " open" not in html.split('class="pd-offrole"')[1].split(">")[0]


def test_pitcher_tucks_hitting_general_and_defense_behind_a_toggle(
    setup, factory, db_conn
):
    client, league, (a, *_) = setup
    team = factory.team(city="Arm", mascot="Barn")
    p = factory.rated_player(team, league, 20, pitcher=True, name="Hurler")
    db_conn.execute(
        """UPDATE player_skills SET strikes = 80, accuracy = 80, stamina = 80,
                  recovery = 80, ground_balls = 80 WHERE player_id = %s""",
        (p.id,),
    )
    html = _panel(client, league, p, a)
    assert _off_role(html) == [["General", "Defense", "Hitting"], ["Pitching"]]


def test_each_player_shows_a_face(setup):
    client, league, (a, b, c, _) = setup
    html = _panel(client, league, a, b, c)
    assert html.count('class="player-face player-face--lg"') == 3
