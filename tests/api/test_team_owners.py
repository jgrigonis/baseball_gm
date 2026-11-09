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


# ── The owner's season review (src/api/services/owner_review.py) ─────────────


def test_owners_review_the_season(lg, factory):
    from src.api.services import owner_review

    x = lg(n=2)
    a, b = x.teams
    factory.gm(team=b, league=x.league, is_ai=True)
    service.ensure(x.db, x.league.id)  # seated before the season starts
    for i in range(3):
        factory.game(
            {"id": x.season.id}, {"id": a.id}, {"id": b.id}, f"2026-04-0{i + 1}"
        )
    # The game factory doesn't write team stats: record a 3-0 start for a.
    for g in x.db.execute(
        "SELECT id FROM games WHERE season_id = %s", (x.season.id,)
    ).fetchall():
        for team, win in ((a.id, 1), (b.id, 0)):
            x.db.execute(
                """INSERT INTO team_game_stats (game_id, team_id, win, loss, runs)
                   VALUES (%s, %s, %s, %s, 5)""",
                (g["id"], team, win, 1 - win),
            )
    out = owner_review.review_season(x.db, x.league.id, x.season.id, 2026)
    assert set(out) == {a.id, b.id}
    row = x.db.execute(
        "SELECT * FROM gm_season_evaluations WHERE gm_id = %s", (x.gm.id,)
    ).fetchone()
    assert row["wins"] == 3 and row["losses"] == 0
    assert row["verdict"] in ("retained", "warned")  # firing is off
    assert row["detail"]["scores"]["wins"] == 1.0
    assert 0 <= row["job_security"] <= 100
    assert out[a.id]["score"] > out[b.id]["score"]
    # Shown on the admin scorecard.
    assert (
        owner_review.security_now(x.db, x.league.id)[a.id]["job_security"]
        == (row["job_security"])
    )


def test_a_new_gm_starts_fresh(lg):
    from src.api.services import owner_review
    from src.league import owner_scoring as sc

    x = lg(n=2)
    owner = service.ensure(x.db, x.league.id)[x.teams[0].id]
    grace = sc.grace(owners.clean_traits(owner["traits"])["patience"])
    before, tenure = owner_review._tenure(x.db, x.gm.id, "someone", owner, 2027)
    assert before == grace and tenure.seasons == 0


# ── The owner's office (src/api/services/owner_office.py) ─────────────────────


def test_the_owner_writes_a_preseason_memo_once(lg, client_for):
    from src.api.services import owner_office

    x = lg(n=2)
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    assert (
        owner_office.catch_up(x.db, x.league.id) == 1
    )  # our team; the other has no GM
    assert owner_office.catch_up(x.db, x.league.id) == 0
    assert owner_office.unseen(x.db, x.gm.id) == 1
    r = client_for(x).get(f"/leagues/{x.league.id}/owner")
    assert "Preseason memo" in r.text and "From the owner" in r.text
    assert owner_office.unseen(x.db, x.gm.id) == 0
    # Opened as a tab (htmx), the page clears the badge in the tab bar.
    tab = client_for(x).get(
        f"/leagues/{x.league.id}/owner", headers={"HX-Request": "true"}
    )
    assert "setOwnerBadge(0)" in tab.text


def test_the_season_review_message(lg, factory):
    from src.api.services import owner_office, owner_review

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    owner_review.review_season(x.db, x.league.id, x.season.id, 2026)
    assert owner_office.review(x.db, x.league.id, x.season.id) == 1
    office = owner_office.office(x.db, x.league.id, x.teams[0].id, x.gm.id)
    assert office["messages"][0]["kind"] == "review"
    assert office["mood"] in [w for _, w in owner_office.om.MOODS]


def test_the_mood_carries_into_next_season_until_its_first_week(lg, factory):
    """Josh saw no owner mood at the start of a season: moods are kept per
    season and the new one has none until a week of games is in."""
    from src.api.services import owner_office

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    team = x.teams[0].id
    x.db.execute(
        """INSERT INTO owner_moods (league_id, team_id, season_id, mood, as_of)
           VALUES (%s, %s, %s, -0.5, NULL)""",
        (x.league.id, team, x.season.id),
    )
    nxt = factory.season(year=2027)
    factory.league_season(x.league, nxt)
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    office = owner_office.office(x.db, x.league.id, team, x.gm.id)
    assert office["mood"] == "frustrated"  # last season's, not blank
    assert owner_office.latest_moods(x.db, x.league.id, 2027) == {team: -0.5}


def test_an_owner_with_no_mood_yet_is_content(lg):
    from src.api.services import owner_office

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    office = owner_office.office(x.db, x.league.id, x.teams[0].id, x.gm.id)
    assert office["mood"] == "content"
