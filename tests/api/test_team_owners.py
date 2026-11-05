# tests/api/test_owners.py
"""Every team's owner in a league (src/api/services/owners.py), the Owner
tab, and the admin's owner pages."""

import html
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import owners as service
from src.db.repositories.owner_repo import OwnerRepository
from src.league import owners


@pytest.fixture
def lg(db_conn, factory):
    def make(n=4):
        league = factory.league(state="season")
        season = factory.season(year=2026)
        factory.league_season(league, season)
        teams = [factory.team(city=f"City{i}", mascot="Club") for i in range(n)]
        for t in teams:
            factory.league_season_team(league, season, t)
        gm = factory.gm(team=teams[0], league=league, is_ai=False)
        return SimpleNamespace(
            db=db_conn, league=league, season=season, teams=teams, gm=gm
        )

    return make


def test_every_team_gets_its_own_owner(lg):
    x = lg()
    by_team = service.ensure(x.db, x.league.id)
    assert set(by_team) == {t.id for t in x.teams}
    assert len({o["owner_id"] for o in by_team.values()}) == len(x.teams)
    for team_id, o in by_team.items():
        assert o["rival_team_id"] != team_id
        assert o["since_year"] == 2026  # the season hasn't started
    # Stored: asking again draws nothing new.
    assert service.ensure(x.db, x.league.id) == by_team


def test_an_owner_who_arrives_mid_season_judges_from_next_season(lg, factory):
    x = lg()
    factory.game({"id": x.season.id}, {"id": x.teams[0].id}, {"id": x.teams[1].id})
    by_team = service.ensure(x.db, x.league.id)
    assert {o["since_year"] for o in by_team.values()} == {2027}


def test_retired_owners_are_never_drawn(lg):
    x = lg()
    repo = OwnerRepository(x.db)
    keep = repo.create(
        "Only Choice",
        "",
        "The Showman",
        owners.clean_weights({}),
        owners.clean_traits({}),
        50,
    )
    x.db.execute("UPDATE owner_personas SET chance = 0 WHERE id <> %s", (keep,))
    by_team = service.ensure(x.db, x.league.id)
    assert {o["owner_id"] for o in by_team.values()} == {keep}  # repeats allowed


def test_the_card_shows_no_numbers(lg):
    x = lg()
    card = service.card(x.db, x.league.id, x.teams[0].id)
    assert card["name"] and card["archetype"]
    assert card["wants"] == owners.wants(card["archetype"])
    assert set(card) == {"name", "bio", "archetype", "wants", "rival", "since_year"}


def test_a_grudge_holder_names_the_rival(lg):
    x = lg(n=2)
    repo = OwnerRepository(x.db)
    grudge = repo.create(
        "Grudge Test",
        "",
        "The Grudge Holder",
        owners.clean_weights({"rivalry": 95}),
        owners.clean_traits({}),
        50,
    )
    calm = repo.create(
        "Calm Test",
        "",
        "The Absentee",
        owners.clean_weights({"rivalry": 10}),
        owners.clean_traits({}),
        50,
    )
    repo.seat(x.league.id, x.teams[0].id, grudge, x.teams[1].id, 2026)
    repo.seat(x.league.id, x.teams[1].id, calm, x.teams[0].id, 2026)
    assert service.card(x.db, x.league.id, x.teams[0].id)["rival"] == "City1 Club"
    assert service.card(x.db, x.league.id, x.teams[1].id)["rival"] is None


@pytest.fixture
def client_for():
    def make(x):
        app.dependency_overrides[get_db] = lambda: x.db
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        me = {"id": x.gm.id, "team_id": x.teams[0].id}
        app.dependency_overrides[get_current_gm] = lambda: me
        app.dependency_overrides[get_gm_or_viewer] = lambda: me
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_the_owner_tab(lg, client_for):
    x = lg()
    r = client_for(x).get(f"/leagues/{x.league.id}/owner")
    assert r.status_code == 200
    text = html.unescape(r.text)
    mine = service.card(x.db, x.league.id, x.teams[0].id)
    assert "Your Owner" in text
    assert mine["name"] in text and mine["wants"] in text
    assert "Owners around the league" in text
    assert f'href="/leagues/{x.league.id}/owner"' in text  # in the tab bar
    for o in service.league_table(x.db, x.league.id):
        assert o["name"] in text
    assert "Patience" not in text and "Spending" not in text
