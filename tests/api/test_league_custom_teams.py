# tests/api/test_league_custom_teams.py
"""Custom leagues: who can join, the warning, and custom teams in the lobby
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


def _league(client, db, custom=True, public=True):
    data = {"name": "Friday Night Ball"}
    if public:
        data["is_public"] = "true"
    if custom:
        data["custom_league"] = "true"
    r = client.post("/leagues/new", data=data)
    league_id = r.headers["location"].split("/")[2]
    return LeagueRepository(db).get_by_id(league_id)


def _pick(client, league_id, team, custom_id):
    return client.post(
        f"/leagues/{league_id}/lobby/custom",
        data={"team": f"{team[0]}|{team[1]}", "custom_team_id": custom_id},
    )


def _in(db, league_id, user):
    return db.execute(
        "SELECT * FROM gms WHERE league_id = %s AND user_id = %s",
        (league_id, user["id"]),
    ).fetchone()


def _gm_team(db, league_id, user):
    gm = _in(db, league_id, user)
    return (gm["lobby_city"], gm["lobby_mascot"])


def _ai_team(db, league_id):
    gm = db.execute(
        """SELECT lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s AND is_ai AND lobby_city IS NOT NULL LIMIT 1""",
        (league_id,),
    ).fetchone()
    return (gm["lobby_city"], gm["lobby_mascot"])


def test_custom_league_is_set_at_creation(as_user, db_conn):
    josh = _user(db_conn)
    league = _league(as_user(josh), db_conn)
    assert league["custom_league"]
    assert not _league(as_user(josh), db_conn, custom=False)["custom_league"]
    # Only paid contributors can make one.
    pat = _user(db_conn, contributor=False)
    r = as_user(pat).post(
        "/leagues/new", data={"name": "Nope", "custom_league": "true"}
    )
    assert r.status_code == 403
    assert "(paid contributors)" in as_user(pat).get("/leagues/new").text


def test_custom_teams_only_go_in_custom_leagues(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn, custom=False)
    html = client.get(f"/leagues/{league['id']}/").text
    assert "Tick Custom league" in html
    r = _pick(
        client,
        league["id"],
        _gm_team(db_conn, league["id"], josh),
        _custom_team(db_conn, josh),
    )
    assert "custom_error=" in r.headers["location"]
    assert lct.assignments(db_conn, league["id"]) == {}


def test_a_custom_league_stays_open_and_public(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    _pick(
        client,
        league["id"],
        _gm_team(db_conn, league["id"], josh),
        _custom_team(db_conn, josh),
    )
    league = LeagueRepository(db_conn).get_by_id(league["id"])
    assert league["is_public"] and league["late_joins"]
    html = client.get(f"/leagues/{league['id']}/").text
    assert league["join_code"] in html
    assert "/settings/is_public" in html
    assert "Custom league" in html and "Super Team" in html


def test_paid_join_by_code_sees_the_custom_teams_first(as_user, db_conn):
    josh, pat = _user(db_conn), _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    _pick(
        client,
        league["id"],
        _gm_team(db_conn, league["id"], josh),
        _custom_team(db_conn, josh),
    )

    other = as_user(pat)
    r = other.post("/leagues/join", data={"join_code": league["join_code"]})
    assert r.status_code == 200
    assert "This league has custom players" in r.text and "Super Team" in r.text
    assert 'name="understood"' in r.text
    assert not _in(db_conn, league["id"], pat)

    r = other.post(
        "/leagues/join", data={"join_code": league["join_code"], "understood": "true"}
    )
    assert r.status_code == 302 and _in(db_conn, league["id"], pat)


def test_unpaid_join_by_code_can_only_watch(as_user, db_conn):
    josh = _user(db_conn)
    league = _league(as_user(josh), db_conn, public=False)
    pat = _user(db_conn, contributor=False)
    other = as_user(pat)
    for understood in ("", "true"):
        r = other.post(
            "/leagues/join",
            data={"join_code": league["join_code"], "understood": understood},
        )
        assert "For paid contributors" in r.text and "Watch it" in r.text
    assert not _in(db_conn, league["id"], pat)
    assert LeagueRepository(db_conn).is_watcher(league["id"], pat["id"])


def test_join_tab(as_user, db_conn):
    josh = _user(db_conn)
    league = _league(as_user(josh), db_conn)

    pat = _user(db_conn, contributor=False)
    other = as_user(pat)
    html = other.get("/leagues/?tab=join").text
    assert "Paid only" in html and ">Custom<" in html
    r = other.post(f"/leagues/{league['id']}/join")
    assert "cant_join=" in r.headers["location"]
    assert not _in(db_conn, league["id"], pat)
    html = other.get(r.headers["location"]).text
    assert "only paid contributors can run a team" in html

    sam = _user(db_conn)
    paid = as_user(sam)
    assert "Paid only" not in paid.get("/leagues/?tab=join").text
    r = paid.post(f"/leagues/{league['id']}/join")
    assert r.status_code == 200 and "This league has custom players" in r.text
    assert not _in(db_conn, league["id"], sam)
    r = paid.post(f"/leagues/{league['id']}/join", data={"understood": "true"})
    assert r.status_code == 302 and _in(db_conn, league["id"], sam)


def test_each_paid_person_sets_their_own_team(as_user, db_conn):
    josh, pat = _user(db_conn), _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    as_user(pat).post(
        "/leagues/join", data={"join_code": league["join_code"], "understood": "true"}
    )
    lid = league["id"]
    pats, ai = _gm_team(db_conn, lid, pat), _ai_team(db_conn, lid)

    # Pat can set his own team, not an AI GM's or Josh's.
    # (Refusals go straight to the service: the route's rollback would undo
    # this test's setup.)
    other = as_user(pat)
    mine = _custom_team(db_conn, pat, name="Pat's Picks")
    for team in (ai, _gm_team(db_conn, lid, josh)):
        with pytest.raises(lct.CustomTeamRefused, match="your own team"):
            lct.assign(db_conn, league, pat, *team, mine)
    assert "custom_error=" not in _pick(other, lid, pats, mine).headers["location"]
    assert lct.assignments(db_conn, lid)[pats]["user_id"] == pat["id"]
    assert "Your team:" in other.get(f"/leagues/{lid}/").text

    # The commissioner can set AI GMs' teams, not Pat's.
    client = as_user(josh)
    theirs = _custom_team(db_conn, josh)
    with pytest.raises(lct.CustomTeamRefused, match="AI GMs' teams"):
        lct.assign(db_conn, league, josh, *pats, theirs)
    assert "custom_error=" not in _pick(client, lid, ai, theirs).headers["location"]
    assert set(lct.assignments(db_conn, lid)) == {pats, ai}

    # Picking another team takes Pat's custom team off his old one.
    others = [
        t
        for t in lobby_teams.league_teams(db_conn, lid)
        if t not in (pats, ai, _gm_team(db_conn, lid, josh))
    ]
    as_user(pat).post(
        f"/leagues/{lid}/lobby/team", data={"team": f"{others[0][0]}|{others[0][1]}"}
    )
    assert set(lct.assignments(db_conn, lid)) == {ai}


def test_leaving_the_lobby_takes_your_custom_team_off(as_user, db_conn):
    from src.api.services.leave_league import leave_league

    josh, pat = _user(db_conn), _user(db_conn)
    league = _league(as_user(josh), db_conn)
    as_user(pat).post(
        "/leagues/join", data={"join_code": league["join_code"], "understood": "true"}
    )
    pats = _gm_team(db_conn, league["id"], pat)
    _pick(as_user(pat), league["id"], pats, _custom_team(db_conn, pat))
    assert pats in lct.assignments(db_conn, league["id"])
    leave_league(db_conn, league["id"], _in(db_conn, league["id"], pat)["id"])
    assert lct.assignments(db_conn, league["id"]) == {}


def test_someone_no_longer_paid_keeps_their_seat(as_user, db_conn):
    josh, pat = _user(db_conn), _user(db_conn)
    league = _league(as_user(josh), db_conn)
    as_user(pat).post(
        "/leagues/join", data={"join_code": league["join_code"], "understood": "true"}
    )
    lapsed = dict(pat, is_contributor=False)
    db_conn.execute(
        "UPDATE users SET is_contributor = FALSE WHERE id = %s", (pat["id"],)
    )
    other = as_user(lapsed)
    assert _in(db_conn, league["id"], pat)
    assert other.get(f"/leagues/{league['id']}/").status_code == 200
    with pytest.raises(lct.CustomTeamRefused, match="paid contributors"):
        lct.assign(
            db_conn,
            league,
            lapsed,
            *_gm_team(db_conn, league["id"], pat),
            _custom_team(db_conn, pat),
        )


def test_taking_over_needs_paid(as_user, db_conn):
    from src.api.services import takeover

    josh = _user(db_conn)
    league = _league(as_user(josh), db_conn)
    started = dict(league, state="offseason")
    pat, sam = _user(db_conn, contributor=False), _user(db_conn)
    assert "paid contributors" in takeover.closed_reason(db_conn, started, pat["id"])
    reason = takeover.closed_reason(db_conn, started, sam["id"]) or ""
    assert "paid contributors" not in reason


def test_a_team_that_is_not_ready_is_refused(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    short = _custom_team(db_conn, josh, keys=READY[:3], name="Short")
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, short)
    assert "custom_error=" in r.headers["location"]
    assert lct.assignments(db_conn, league["id"]) == {}


def test_only_your_own_custom_teams(as_user, db_conn):
    josh, pat = _user(db_conn), _user(db_conn)
    client = as_user(josh)
    league = _league(client, db_conn)
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    r = _pick(client, league["id"], first, _custom_team(db_conn, pat))
    assert "custom_error=" in r.headers["location"]
    assert lct.assignments(db_conn, league["id"]) == {}


def test_non_contributors_get_no_card_in_an_ordinary_league(as_user, db_conn):
    client = as_user(_user(db_conn, contributor=False))
    league = _league(client, db_conn, custom=False)
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
    out, made = lct.apply(db_conn, league["id"], generated, random.Random(4))
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
