# tests/api/test_league_custom_teams.py
"""Custom teams in a single-player league's lobby
(services/league_custom_teams.py)."""

import random
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import league_custom_teams as lct
from src.api.services import lobby_teams
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.db.repositories.league_repo import LeagueRepository
from src.league.real_seasons import players
from src.team.team_factory import TeamFactory


def _user(db, contributor=True):
    uid = str(uuid.uuid4())
    db.execute(
        """INSERT INTO users (id, session_token, display_name, username,
                              password_hash, is_contributor)
           VALUES (%s, %s, %s, %s, 'x', %s)""",
        (uid, uid, uid[:8], uid[:8], contributor),
    )
    return {
        "id": uid,
        "username": uid[:8],
        "display_name": uid[:8],
        "has_password": True,
        "is_admin": False,
        "is_contributor": contributor,
    }


@pytest.fixture
def as_user(db_conn):
    who = {}
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: who["user"]

    def switch(user):
        who["user"] = user
        return TestClient(app, follow_redirects=False)

    yield switch
    app.dependency_overrides.clear()


def _keys(pos, n, year=2001):
    found = [s for s in players._all()[0] if s.year == year and s.pos == pos]
    return [s.key for s in found[:n]]


READY = _keys("sp", 5) + _keys("rp", 6) + _keys("c", 1) + _keys("ss", 2)


def _custom_team(db, user, keys=READY, name="Super Team", edits=None):
    repo = CustomTeamRepository(db)
    entries = [{"key": k, "skills": None} for k in keys]
    if edits:
        entries[0]["skills"] = edits
    return repo.create(user["id"], name, uuid.uuid4().hex[:8].upper(), entries)


def _league(client, db):
    r = client.post("/leagues/new", data={"name": "Solo", "is_public": "true"})
    league_id = r.headers["location"].split("/")[2]
    return LeagueRepository(db).get_by_id(league_id)


def _pick(client, league_id, team, custom_id):
    return client.post(
        f"/leagues/{league_id}/lobby/custom",
        data={"team": f"{team[0]}|{team[1]}", "custom_team_id": custom_id},
    )


def test_a_custom_team_makes_the_league_single_player(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    team_id = _custom_team(db_conn, josh)
    html = client.get(f"/leagues/{league['id']}/").text
    assert "Custom Teams" in html and "Super Team" in html

    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, team_id)
    assert r.status_code == 303
    league = LeagueRepository(db_conn).get_by_id(league["id"])
    assert league["single_player"] and not league["is_public"]
    assert not league["late_joins"]
    chosen = lct.assignments(db_conn, league["id"])[first]
    assert chosen["name"] == "Super Team" and len(chosen["players"]) == len(READY)

    html = client.get(f"/leagues/{league['id']}/").text
    assert "nobody else can join" in html
    assert league["join_code"] not in html

    # The code no longer lets anyone in.
    pat = _user(db_conn, contributor=False)
    other = as_user(pat)
    r = other.post("/leagues/join", data={"join_code": league["join_code"]})
    assert "single player" in r.text
    other.post(f"/leagues/{league['id']}/join")
    assert not db_conn.execute(
        "SELECT 1 FROM gms WHERE league_id = %s AND user_id = %s",
        (league["id"], pat["id"]),
    ).fetchone()

    # Taking it off again opens the league back up.
    client = as_user(josh)
    _pick(client, league["id"], first, "")
    assert not LeagueRepository(db_conn).get_by_id(league["id"])["single_player"]
    assert lct.assignments(db_conn, league["id"]) == {}


def test_commissioner_cannot_reopen_a_single_player_league(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    _pick(client, league["id"], first, _custom_team(db_conn, josh))
    r = client.post(f"/leagues/{league['id']}/settings/is_public", data={"on": "true"})
    assert r.status_code == 422
    assert not LeagueRepository(db_conn).get_by_id(league["id"])["is_public"]


def test_a_team_that_is_not_ready_is_refused(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    short = _custom_team(db_conn, josh, keys=READY[:3], name="Short")
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, short)
    assert "custom_error=" in r.headers["location"]
    assert lct.assignments(db_conn, league["id"]) == {}
    assert not LeagueRepository(db_conn).get_by_id(league["id"])["single_player"]


def test_only_your_own_custom_teams(as_user, db_conn):
    josh, pat = _user(db_conn), _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, _custom_team(db_conn, pat))
    assert "custom_error=" in r.headers["location"]
    assert lct.assignments(db_conn, league["id"]) == {}


def test_not_once_someone_else_has_joined(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    as_user(_user(db_conn, contributor=False)).post(
        "/leagues/join", data={"join_code": league["join_code"]}
    )
    client = as_user(josh)
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, _custom_team(db_conn, josh))
    assert "custom_error=" in r.headers["location"]
    assert "others have joined" in client.get(f"/leagues/{league['id']}/").text


def test_non_contributors_get_no_card(as_user, db_conn):
    client = as_user(_user(db_conn, contributor=False))
    league = _league(client, db_conn)
    assert "Custom Teams" not in client.get(f"/leagues/{league['id']}/").text


def test_apply_swaps_in_the_players_and_fills_to_26(as_user, db_conn):
    josh = _user(db_conn)
    league = _league(as_user(josh), db_conn)
    teams = lobby_teams.league_teams(db_conn, league["id"])
    edited = dict(players.get(READY[0]).skills, stamina=100)
    custom_id = _custom_team(db_conn, josh, edits=edited)
    lct.assign(db_conn, league, josh, *teams[0], custom_id)

    factory = TeamFactory(rng=random.Random(3))
    generated = [factory.generate_team(city=c, mascot=m, size=26) for c, m in teams]
    out = lct.apply(db_conn, league["id"], generated, random.Random(4))
    assert out[1:] == generated[1:]
    mine = out[0]
    assert (mine.city, mine.mascot) == teams[0]
    assert len(mine.players) == 26
    names = {f"{p.first_name} {p.last_name}" for p in mine.players}
    for key in READY:
        assert players.get(key).name in names
    pitchers = [p for p in mine.players if p.position in ("sp", "rp")]
    assert len(pitchers) == 13  # 11 of his, 2 generated
    first = next(p for p in mine.players if p.last_name == players.get(READY[0]).last)
    assert first.skills["stamina"] == 100
