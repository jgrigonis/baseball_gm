# tests/api/test_custom_players.py
"""Made-up players: the player creator, My Players, custom teams holding
them, and a league starting with one (routers/custom_players.py,
services/custom_players.py)."""

import copy
import random
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import custom_players as cp
from src.api.services import custom_teams as ct
from src.api.services import league_custom_teams as lct
from src.api.services import lobby_teams
from src.api.services.league_start import start_league
from src.db.repositories.custom_player_repo import CustomPlayerRepository
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.db.repositories.league_repo import LeagueRepository
from src.league.real_seasons import SKILLS, players
from src.player import face as face_mod
from src.player import happiness as hp


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


def _rolled(pos="cf", seed=1):
    return cp.roll(random.Random(seed), position=pos)


def _create(client, player, team=""):
    r = client.post("/my-players/", json={"player": player, "team": team})
    assert r.status_code == 200, r.text
    return r.json()


# ── rolling and checking ────────────────────────────────────────────────


def test_a_rolled_player_is_complete_and_saves_as_is():
    for pos in ("sp", "c", "dh", None):
        p = cp.roll(random.Random(7), position=pos)
        if pos:
            assert p["position"] == pos
        assert set(p["skills"]) == set(SKILLS)
        assert all(p["caps"][s] >= p["skills"][s] for s in SKILLS)
        assert cp.AGE_MIN <= p["age"] <= cp.AGE_MAX
        assert p["personality"]["type"] in hp.TYPES
        assert p["first_name"] and p["first_name"] != p["first_name"].upper()
        assert cp.clean(copy.deepcopy(p)) == {
            **p,
            "face": face_mod.clean_traits(p["face"]),
        }


def test_a_roll_grows_him_to_the_age_picked():
    # Made at 17 and aged up: a 17-year-old is raw, a 28-year-old isn't.
    young = [cp.roll(random.Random(i), position="ss", age=17) for i in range(20)]
    prime = [cp.roll(random.Random(i), position="ss", age=28) for i in range(20)]
    assert {p["age"] for p in young} == {17} and {p["age"] for p in prime} == {28}

    def avg(ps):
        return sum(sum(p["skills"].values()) for p in ps) / len(ps)

    assert avg(prime) > avg(young)


def test_clean_says_what_to_fix():
    p = _rolled()
    bad = copy.deepcopy(p)
    bad["skills"]["power"] = 101
    with pytest.raises(cp.CustomPlayerError, match="Power has to be from 1 to 100"):
        cp.clean(bad)
    bad = copy.deepcopy(p)
    bad["last_name"] = "  "
    with pytest.raises(cp.CustomPlayerError, match="last name"):
        cp.clean(bad)
    bad = copy.deepcopy(p)
    bad["position"] = "p"
    with pytest.raises(cp.CustomPlayerError, match="position"):
        cp.clean(bad)
    bad = copy.deepcopy(p)
    bad["jersey_prefs"] = ["7", "101"]
    with pytest.raises(cp.CustomPlayerError, match="101"):
        cp.clean(bad)
    # A ceiling under his rating is lifted to it, not refused.
    low = copy.deepcopy(p)
    low["skills"]["speed"] = 80
    low["caps"]["speed"] = 20
    assert cp.clean(low)["caps"]["speed"] == 80


# ── the creator and My Players ─────────────────────────────────────────


def test_contributor_makes_and_edits_a_player(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    html = client.get("/my-players/new?pos=ss").text
    assert "New player" in html and '"position": "ss"' in html
    assert client.get("/my-players/roll?pos=c").json()["position"] == "c"
    assert client.get("/my-players/name").json()["last_name"]

    p = _rolled("ss")
    p["first_name"], p["last_name"] = "Rocket", "Ramirez"
    p["caps"]["contact"] = 99
    p["personality"]["ruiner"] = True
    saved = _create(client, p)
    row = CustomPlayerRepository(db_conn).get(saved["id"])
    assert row["owner_id"] == josh["id"]
    assert row["caps"]["contact"] == 99 and row["personality"]["ruiner"] is True
    assert saved["url"] == "/teams/#my-players"

    teams_page = client.get("/teams/").text
    assert "My Players" in teams_page and "Rocket Ramirez" in teams_page

    p["skills"]["power"] = 77
    r = client.post(f"/my-players/{saved['id']}", json={"player": p})
    assert r.json()["ok"]
    assert CustomPlayerRepository(db_conn).get(saved["id"])["skills"]["power"] == 77

    bad = dict(p, age=60)
    r = client.post(f"/my-players/{saved['id']}", json={"player": bad})
    assert r.status_code == 400 and "Age" in r.json()["error"]


def test_only_contributors_and_only_their_own(as_user, db_conn):
    pat = _user(db_conn, contributor=False)
    client = as_user(pat)
    assert client.get("/my-players/new").status_code == 403
    assert client.post("/my-players/", json={"player": _rolled()}).status_code == 403
    assert "for paid contributors" in client.get("/teams/").text

    josh, sam = _user(db_conn), _user(db_conn)
    made = _create(as_user(josh), _rolled())["id"]
    other = as_user(sam)
    assert other.get(f"/my-players/{made}").status_code == 404
    assert (
        other.post(f"/my-players/{made}", json={"player": _rolled()}).status_code == 404
    )
    assert other.post(f"/my-players/{made}/delete").status_code == 404


def test_made_players_go_on_custom_teams(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    team_id = (
        client.post("/teams/", data={"name": "Mixed"})
        .headers["location"]
        .rsplit("/", 1)[1]
    )

    # Made from the team page: saved and put straight on the team.
    p = _rolled("c")
    p["first_name"], p["last_name"] = "Made", "Catcher"
    saved = _create(client, p, team=team_id)
    assert saved["added"] and saved["url"] == f"/teams/{team_id}#roster"
    team = CustomTeamRepository(db_conn).get(team_id)
    assert team["players"] == [{"key": f"made:{saved['id']}", "made": saved["id"]}]

    html = client.get(f"/teams/{team_id}").text
    assert "Made Catcher" in html and ">Made<" in html
    rows = ct.roster(team, db_conn)
    assert rows[0]["made"] and rows[0]["pos"] == "c"
    assert ct.summary(rows)["needs"] == [
        "at least 10 pitchers",
        "at least 5 starting pitchers",
    ]
    # His name on the roster opens the player creator.
    r = client.get(f"/teams/{team_id}/players/0")
    assert (
        r.status_code == 303
        and r.headers["location"] == f"/my-players/{saved['id']}?team={team_id}"
    )

    # One already made goes on from the My Players tab.
    other = _create(client, _rolled("sp"))["id"]
    r = client.post(f"/teams/{team_id}/add-made", data={"made_id": other})
    assert r.status_code == 303
    r = client.post(f"/teams/{team_id}/add-made", data={"made_id": other})
    assert (
        "already+on+the+team" in r.headers["location"]
        or "already%20on" in r.headers["location"]
    )
    assert len(CustomTeamRepository(db_conn).get(team_id)["players"]) == 2

    # Deleting him takes him off the team.
    client.post(f"/my-players/{saved['id']}/delete")
    assert CustomPlayerRepository(db_conn).get(saved["id"]) is None
    keys = [e["key"] for e in CustomTeamRepository(db_conn).get(team_id)["players"]]
    assert keys == [f"made:{other}"]


def test_a_saved_copy_gets_its_own_made_players(as_user, db_conn):
    josh, sam = _user(db_conn), _user(db_conn)
    client = as_user(josh)
    team_id = (
        client.post("/teams/", data={"name": "Shared"})
        .headers["location"]
        .rsplit("/", 1)[1]
    )
    made = _create(client, _rolled(), team=team_id)["id"]
    code = CustomTeamRepository(db_conn).get(team_id)["share_code"]

    assert (
        "Made"
        in as_user(_user(db_conn, contributor=False)).get(f"/teams/shared/{code}").text
    )
    other = as_user(sam)
    copy_id = (
        other.post(f"/teams/shared/{code}/copy").headers["location"].rsplit("/", 1)[1]
    )
    entry = CustomTeamRepository(db_conn).get(copy_id)["players"][0]
    assert entry["made"] != made
    mine = CustomPlayerRepository(db_conn).get(entry["made"])
    assert mine["owner_id"] == sam["id"]
    assert mine["skills"] == CustomPlayerRepository(db_conn).get(made)["skills"]


# ── into a league ──────────────────────────────────────────────────────


def test_a_league_starts_with_a_made_player_as_he_was_made(as_user, db_conn):
    josh = _user(db_conn)
    client = as_user(josh)
    p = _rolled("cf", seed=5)
    p["first_name"], p["last_name"] = "Zed", "Madeup"
    p["skills"]["speed"], p["caps"]["speed"] = 70, 95
    p["face"]["facial_hair"] = "beard"
    p["home_region"] = "Oceania"
    p["jersey_prefs"] = ["42"]
    p["personality"] = {
        "type": "Grinder",
        "traits": {"ego": 10, "temper": 90, "loyalty": 70},
        "drives": {d: 50 for d in hp.DRIVES},
        "climate": "cold",
        "ruiner": True,
    }
    made = _create(client, p)["id"]
    repo = CustomTeamRepository(db_conn)
    team_id = repo.create(
        josh["id"],
        "Solo Stars",
        uuid.uuid4().hex[:8].upper(),
        [{"key": k, "skills": None} for k in READY],
    )
    ct.add_made(repo, repo.get(team_id), CustomPlayerRepository(db_conn).get(made))

    r = client.post("/leagues/new", data={"name": "Solo", "custom_league": "true"})
    league = LeagueRepository(db_conn).get_by_id(r.headers["location"].split("/")[2])
    first = lobby_teams.league_teams(db_conn, league["id"])[0]
    lct.assign(db_conn, league, josh, *first, team_id)
    db_conn.commit()

    # Later edits don't reach the league's copy.
    later = dict(p, last_name="Changed")
    client.post(f"/my-players/{made}", json={"player": later})
    entry = next(
        e
        for e in lct.assignments(db_conn, league["id"])[first]["players"]
        if e.get("made")
    )
    assert entry["player"]["last_name"] == "Madeup"

    start_league(league["id"], db_conn)
    row = db_conn.execute(
        """SELECT p.id, p.face, p.home_region, p.jersey_prefs, sk.speed, sk.age
           FROM players p JOIN player_skills sk ON sk.player_id = p.id
           WHERE p.league_id = %s AND p.last_name = 'Madeup'""",
        (league["id"],),
    ).fetchone()
    assert row is not None
    assert row["speed"] == 70 and row["age"] == p["age"]
    assert row["face"]["facial_hair"] == "beard"
    assert row["home_region"] == "Oceania" and row["jersey_prefs"] == ["42"]
    caps = db_conn.execute(
        "SELECT speed FROM player_talent_caps WHERE player_id = %s", (row["id"],)
    ).fetchone()
    assert caps["speed"] == 95
    pers_row = db_conn.execute(
        "SELECT * FROM player_personality WHERE player_id = %s", (row["id"],)
    ).fetchone()
    pers = hp.Personality.from_row(dict(pers_row))
    assert pers.type == "Grinder" and pers.ruiner and pers.climate == "cold"
    assert pers.traits == {"ego": 10, "temper": 90, "loyalty": 70}

    # His face is the one picked for him, in lists and in the panel.
    svg = client.get(f"/faces/{row['id']}.svg?age={p['age']}").text
    assert svg == face_mod.face_svg(row["id"], p["age"], None, None, row["face"])
    assert svg != face_mod.face_svg(row["id"], p["age"], None, None)


def test_a_stored_ruiner_wins_over_the_id_draw():
    traits = {"ego": 50, "temper": 50, "loyalty": 50}
    row = {"player_id": "abc", "type": "Easygoing", "drives": {}, "traits": traits}
    drawn = hp.Personality.from_row(row).ruiner
    assert hp.Personality.from_row({**row, "ruiner": not drawn}).ruiner is (not drawn)
    assert hp.Personality.from_row({**row, "ruiner": None}).ruiner is drawn
