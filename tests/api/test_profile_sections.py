# tests/api/test_profile_sections.py
"""The GM profile's draft record, trades, GM style and timeline
(view_models/profile_sections.py)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import career
from src.api.view_models.profile_sections import sections


def _id():
    return str(uuid.uuid4())


@pytest.fixture
def world(db_conn, factory):
    """Josh runs Amsterdam in a 2030 league; Tokyo is an AI team."""
    league = factory.league(state="season")
    db_conn.execute(
        "UPDATE leagues SET name = 'Weekend League' WHERE id = %s", (league.id,)
    )
    season = factory.season(year=2030)
    factory.league_season(league, season)
    mine = factory.team(city="Amsterdam", mascot="Captains")
    other = factory.team(city="Tokyo", mascot="Samurai")
    gm = factory.gm(team=mine, league=league, is_ai=False)
    ai = factory.gm(team=other, league=league)
    user = _id()
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'Josh', %s)",
        (user, user, f"josh-{user[:8]}"),
    )
    db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (user, gm.id))
    draft = factory.draft(league=league, season=season, state="complete")
    return {"league": league, "season": season, "mine": mine, "other": other,
            "gm": gm, "ai": ai, "user": user, "draft": draft}  # fmt: skip


def _player(db, w, first, last, position="ss", age=21):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, %s, %s, 'R', 'R', %s, %s)",
        (pid, first, last, position, w["league"].id),
    )
    db.execute(
        """INSERT INTO player_skills (player_id, age, durability, clutch, speed, power, eye,
               contact, base_running, bunting, catching, infield, outfield, arm, accuracy,
               stamina, recovery, ground_balls, strikes)
           VALUES (%s, %s, 50,50,50,50,50,50,50,50,50,50,50,50,50,50,50,50,50)""",
        (pid, age),
    )
    return pid


def _pick(db, w, pid, pick, rnd=1, gm=None):
    db.execute(
        """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (w["draft"].id, pick, rnd, (gm or w["gm"]).id, w["mine"].id, pid),
    )


def _all_star(db, w, pid):
    db.execute(
        "INSERT INTO all_stars (season_id, player_id, team_id, slot) VALUES (%s, %s, %s, 'ss')",
        (w["season"].id, pid, w["mine"].id),
    )


def _trade(db, w, sent, got, pick_round=None):
    oid = _id()
    db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id, to_team_id,
               from_gm_id, status, created_on)
           VALUES (%s, %s, %s, %s, %s, %s, 'accepted', '2030-06-01')""",
        (oid, w["league"].id, w["season"].id, w["mine"].id, w["other"].id, w["gm"].id),
    )
    for pid in sent:
        db.execute(
            "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id) VALUES (%s, %s, %s)",
            (oid, pid, w["mine"].id),
        )
    for pid in got:
        db.execute(
            "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id) VALUES (%s, %s, %s)",
            (oid, pid, w["other"].id),
        )
    if pick_round:
        db.execute(
            """INSERT INTO trade_offer_picks (offer_id, draft_year, round, original_team_id, from_team_id)
               VALUES (%s, 2031, %s, %s, %s)""",
            (oid, pick_round, w["other"].id, w["other"].id),
        )


def _season(db, w, **cols):
    row = {
        "user_id": w["user"], "league_id": w["league"].id, "season_id": w["season"].id,
        "league_name": "Weekend League", "season_year": 2030, "team_city": "Amsterdam",
        "team_mascot": "Captains", "wins": 81, "losses": 81, "final": True, **cols,
    }  # fmt: skip
    names = ", ".join(row)
    marks = ", ".join(f"%({k})s" for k in row)
    db.execute(f"INSERT INTO gm_career_seasons ({names}) VALUES ({marks})", row)


def _sections(db, w):
    seasons = db.execute(
        "SELECT * FROM gm_career_seasons WHERE user_id = %s", (w["user"],)
    ).fetchall()
    return sections(db, w["user"], [dict(s) for s in seasons])


class TestDraft:
    def test_no_picks_no_section(self, db_conn, world):
        assert _sections(db_conn, world)["draft"] is None

    def test_best_picks_are_the_all_stars(self, db_conn, world):
        a = _player(db_conn, world, "Marco", "Vos", "p")
        b = _player(db_conn, world, "Ines", "Barros")
        c = _player(db_conn, world, "Plain", "Pick")
        _pick(db_conn, world, a, 4)
        _pick(db_conn, world, b, 41, rnd=2)
        _pick(db_conn, world, c, 70, rnd=3)
        _all_star(db_conn, world, a)
        _all_star(db_conn, world, b)
        other_season = db_conn.execute(
            "INSERT INTO seasons (id, year, name) VALUES (%s, 2031, 'S') RETURNING id",
            (_id(),),
        ).fetchone()["id"]
        db_conn.execute(
            "INSERT INTO all_stars (season_id, player_id, team_id, slot) VALUES (%s, %s, %s, 'p')",
            (other_season, a, world["mine"].id),
        )

        d = _sections(db_conn, world)["draft"]

        assert (d["picks"], d["all_stars"]) == (3, 2)
        assert [p["name"] for p in d["best"]] == ["Marco Vos", "Ines Barros"]
        assert d["best"][0]["became"] == "2× All-Star"
        assert d["best"][0]["when"] == "2030 · R1 #4"

    def test_without_all_stars_shows_the_top_picks(self, db_conn, world):
        _pick(db_conn, world, _player(db_conn, world, "Late", "One"), 30, rnd=2)
        _pick(db_conn, world, _player(db_conn, world, "First", "One"), 2)
        d = _sections(db_conn, world)["draft"]
        assert not d["any_stars"]
        assert d["best"][0]["name"] == "First One"

    def test_ai_picks_dont_count(self, db_conn, world):
        _pick(db_conn, world, _player(db_conn, world, "A", "I"), 1, gm=world["ai"])
        assert _sections(db_conn, world)["draft"] is None


class TestTrades:
    def test_recent_trades_say_who_went_where(self, db_conn, world):
        luca = _player(db_conn, world, "Luca", "Ferro")
        hana = _player(db_conn, world, "Hana", "Sato")
        _trade(db_conn, world, [luca], [hana], pick_round=1)
        _season(db_conn, world, trades=1)

        t = _sections(db_conn, world)["trades"]

        assert (t["accepted"], t["offered"]) == (1, 1)
        (r,) = t["recent"]
        assert r["sent"] == "Luca Ferro"
        assert r["got"] == "Hana Sato and Tokyo's 2031 round 1 pick"
        assert (r["city"], r["year"]) == ("Tokyo", 2030)

    def test_no_trades_no_section(self, db_conn, world):
        assert _sections(db_conn, world)["trades"] is None


class TestStyle:
    def _style(self, db, w):
        return {r["label"]: r for r in _sections(db, w)["style"]}

    def test_win_now_front_office(self, db_conn, factory, world):
        _season(db_conn, world, front_office="contending")
        s = self._style(db_conn, world)
        assert s["Front office"]["word"] == "Win-now"
        assert s["Front office"]["why"] == "Contending or all-in 1 of 1 season"

    def test_draft_lean_and_age(self, db_conn, world):
        for i in range(3):
            pid = _player(db_conn, world, "P", str(i), "p", age=22)
            _pick(db_conn, world, pid, i + 1)
        s = self._style(db_conn, world)
        assert s["Draft"]["word"] == "Pitching first"
        assert s["Draft age"]["word"] == "Ready sooner"  # 22 when picked

    def test_settings(self, db_conn, world):
        db_conn.execute(
            "UPDATE gm_profiles SET lineup_style = 'analytics', baserunning = 'aggressive'"
            " WHERE gm_id = %s",
            (world["gm"].id,),
        )
        s = self._style(db_conn, world)
        assert s["Lineups"]["word"] == "Analytics"
        assert s["Lineups"]["why"] == "Aggressive on the bases"
        assert s["Pitching"]["word"] == "Strict pitch counts"


class TestTimeline:
    def test_newest_first_title_first(self, db_conn, world):
        _season(db_conn, world, playoff_result="Champion", division_title=True,
                wins=101, losses=61, sweeps=1)  # fmt: skip
        _trade(db_conn, world, [_player(db_conn, world, "Luca", "Ferro")], [])
        texts = [e["text"] for e in _sections(db_conn, world)["timeline"]]
        assert texts == [
            "Won the title with the Amsterdam Captains",
            "Swept a playoff series",
            "Won the division (101-61)",
            "A 101-win season",
            "Traded Luca Ferro to Tokyo for nothing",
        ]


class TestCareerKeepsTheFrontOffice:
    def test_front_office_saved_with_the_season(self, db_conn, world):
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
                   winner_id, completed) VALUES (%s, '2030-05-01', %s, %s, %s, %s, 1)""",
            (
                g := _id(),
                world["season"].id,
                world["mine"].id,
                world["other"].id,
                world["mine"].id,
            ),
        )
        for team, won in ((world["mine"], 1), (world["other"], 0)):
            db_conn.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss) VALUES (%s, %s, 1, %s, %s)",
                (g, team.id, won, 1 - won),
            )
        db_conn.execute(
            """INSERT INTO team_states (league_id, season_id, team_id, as_of, state, candidate, inputs)
               VALUES (%s, %s, %s, '2030-05-01', 'rebuilding', 'rebuilding', '{}')""",
            (world["league"].id, world["season"].id, world["mine"].id),
        )
        career.record_league(db_conn, world["league"].id)
        row = db_conn.execute(
            "SELECT front_office FROM gm_career_seasons WHERE user_id = %s",
            (world["user"],),
        ).fetchone()
        assert row["front_office"] == "rebuilding"


class TestPage:
    def test_sections_on_the_profile(self, db_conn, world):
        pid = _player(db_conn, world, "Marco", "Vos", "p")
        _pick(db_conn, world, pid, 4)
        _all_star(db_conn, world, pid)
        _trade(db_conn, world, [_player(db_conn, world, "Luca", "Ferro")], [pid])
        _season(
            db_conn, world, playoff_result="Champion", trades=1, front_office="all-in"
        )
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": world["user"]}
        try:
            name = db_conn.execute(
                "SELECT username FROM users WHERE id = %s", (world["user"],)
            ).fetchone()["username"]
            html = TestClient(app).get(f"/gms/{name}").text
        finally:
            app.dependency_overrides.clear()
        for text in ("Draft record · 1 pick", "Marco Vos", "Trades", "Luca Ferro",
                     "GM style", "Win-now", "Timeline", "Won the title"):  # fmt: skip
            assert text in html, text
