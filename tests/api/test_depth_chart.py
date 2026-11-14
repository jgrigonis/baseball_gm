# tests/api/test_depth_chart.py
"""The Depth Chart tab (view_models/depth_chart.py, Josh 2026-11-14). It
follows the team's saved lineup, rotation and bullpen roles."""

import random
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.view_models.depth_chart import depth_chart

SKILLS = (
    "strikes stamina recovery accuracy clutch speed power arm eye contact"
    " base_running bunting catching infield outfield ground_balls"
).split()


def _vary(db, pid, rng, base):
    sets = ", ".join(f"{s} = %s" for s in SKILLS)
    vals = [max(15, min(95, base + rng.randint(-25, 25))) for _ in SKILLS]
    db.execute(f"UPDATE player_skills SET {sets} WHERE player_id = %s", (*vals, pid))


@pytest.fixture
def lg(db_conn, factory):
    rng = random.Random(7)
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    teams = [factory.team(city=f"City{i}", mascot=f"Mascots{i}") for i in range(4)]
    for t in teams:
        factory.league_season_team(league, season, t)
    mine = teams[0]
    gm = factory.gm(team=mine, league=league, is_ai=False)
    for t_i, t in enumerate(teams):
        base = 60 if t_i == 0 else 50
        for i in range(14):
            p = factory.rated_player(t, league, status="26man", name=f"Bat{t_i}{i}")
            _vary(db_conn, p.id, rng, base)
        for i in range(12):
            p = factory.rated_player(
                t, league, status="26man", pitcher=True, name=f"Arm{t_i}{i}"
            )
            _vary(db_conn, p.id, rng, base)
        if t_i == 0:
            for i in range(4):
                p = factory.rated_player(t, league, status="minors", name=f"Kid{i}")
                _vary(db_conn, p.id, rng, base)
    return {"league": league, "season": season, "mine": mine, "teams": teams, "gm": gm}


def test_depth_chart_groups_and_backups(db_conn, lg):
    d = depth_chart(db_conn, lg["league"].id, lg["season"].id, lg["mine"].id)
    assert [e["slot"] for e in d["rotation"]] == ["SP1", "SP2", "SP3", "SP4", "SP5"]
    assert d["bullpen"][0]["slot"] == "CL"
    assert len(d["bullpen"]) == 6
    assert [e["slot"] for e in d["defense"]] == [
        "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF",
    ]  # fmt: skip
    assert len(d["bats"]) == 9
    starters = {e["id"] for e in d["defense"]}
    for e in d["defense"]:
        assert all(b["id"] not in starters for b in e["backups"])
        assert len(e["backups"]) <= 2
    # The better team ranks near the top in each area, out of four.
    assert all(
        g["rank"] <= 2 and g["rank_text"].endswith(" of 4")
        for g in d["groups"].values()
    )
    assert not any(g["weak"] for g in d["groups"].values())


def _ids(db, team, pitchers):
    return [
        r["id"]
        for r in db.execute(
            """SELECT p.id FROM players p JOIN team_players tp ON tp.player_id = p.id
               WHERE tp.team_id = %s AND p.last_name LIKE %s ORDER BY p.last_name""",
            (team.id, "Arm%" if pitchers else "Bat%"),
        ).fetchall()
    ]


def test_follows_the_saved_lineup_rotation_and_roles(db_conn, lg):
    """Josh: the depth chart should match the Lineup tab, not its own picks."""
    mine, season = lg["mine"], lg["season"]
    bats, arms = _ids(db_conn, mine, False), _ids(db_conn, mine, True)
    spots = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]
    # The last nine hitters, in a made-up order a person might save.
    order = list(reversed(bats[-9:]))
    for i, (pid, pos) in enumerate(zip(order, spots), 1):
        db_conn.execute(
            """INSERT INTO gm_lineup_preferences
               (gm_id, player_id, batting_order, position, vs_hand)
               VALUES (%s, %s, %s, %s, 'R')""",
            (lg["gm"].id, pid, i, pos.upper()),
        )
    rotation = arms[7:12]
    for i, pid in enumerate(rotation, 1):
        db_conn.execute(
            """INSERT INTO team_rotations
               (team_id, season_id, player_id, rotation_order, effective_date)
               VALUES (%s, %s, %s, %s, '2025-03-01')""",
            (mine.id, season.id, pid, i),
        )
    roles = {arms[0]: "Long", arms[1]: "Setup", arms[2]: "Closer", arms[3]: "Middle"}
    for pid, role in roles.items():
        db_conn.execute(
            """INSERT INTO bullpen_roles
               (team_id, player_id, season_id, role, effective_date)
               VALUES (%s, %s, %s, %s, '2025-03-01')""",
            (mine.id, pid, season.id, role),
        )

    d = depth_chart(db_conn, lg["league"].id, season.id, mine.id)
    assert d["from_lineup"]
    assert [e["id"] for e in d["bats"]] == order
    assert [e["pos"] for e in d["bats"]] == [s.upper() for s in spots]
    assert [e["id"] for e in d["defense"]] == order[:8]
    assert d["dh"]["id"] == order[8]
    assert d["groups"]["bats"]["label"] == "Batting order"
    assert [e["id"] for e in d["rotation"]] == rotation
    assert [(e["id"], e["slot"]) for e in d["bullpen"]] == [
        (arms[2], "CL"), (arms[1], "SU"), (arms[3], "MR"), (arms[0], "LR"),
    ]  # fmt: skip


def test_nothing_saved_falls_back_to_ratings(db_conn, lg):
    d = depth_chart(db_conn, lg["league"].id, lg["season"].id, lg["mine"].id)
    assert not d["from_lineup"]
    assert d["groups"]["bats"]["label"] == "Best 9 bats"


def test_not_in_the_league(db_conn, lg, factory):
    other = factory.team(city="Far", mascot="Away")
    assert depth_chart(db_conn, lg["league"].id, lg["season"].id, other.id) is None
    assert depth_chart(db_conn, lg["league"].id, None, lg["mine"].id) is None


class TestPages:
    @pytest.fixture
    def client(self, db_conn, lg):
        user_id = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'J')",
            (user_id, user_id),
        )
        db_conn.execute(
            "UPDATE gms SET user_id = %s WHERE id = %s", (user_id, lg["gm"].id)
        )
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id, "username": None, "has_password": False,
        }  # fmt: skip
        me = {"id": lg["gm"].id, "team_id": lg["mine"].id}
        app.dependency_overrides[get_gm_or_viewer] = lambda: me
        app.dependency_overrides[get_current_gm] = lambda: me
        yield TestClient(app, follow_redirects=False)
        app.dependency_overrides.clear()

    def test_depth_tab_any_team(self, client, lg):
        url = f"/leagues/{lg['league'].id}/depth"
        r = client.get(url, headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert "Depth Chart" in r.text and "dc-field" in r.text
        assert "City0 Mascots0 (you)" in r.text
        other = lg["teams"][2]
        r = client.get(f"{url}?team_id={other.id}", headers={"HX-Request": "true"})
        assert f'value="{other.id}" selected' in r.text

    def test_lineup_tab_has_no_cards(self, client, lg):
        r = client.get(
            f"/leagues/{lg['league'].id}/lineup", headers={"HX-Request": "true"}
        )
        assert r.status_code == 200 and "/depth/cards" not in r.text

    def test_sidebar_has_the_tab(self, client, lg):
        r = client.get(f"/leagues/{lg['league'].id}/depth")
        assert "Depth Chart" in r.text and f"/leagues/{lg['league'].id}/depth" in r.text
