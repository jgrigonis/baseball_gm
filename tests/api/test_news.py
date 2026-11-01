# tests/api/test_news.py
"""The league news feed (src/api/services/news/, plans/news-feed.md): stories
written after each sim job, crediting the GMs behind the moves, and the
News tab that shows them."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import news
from src.api.services.news.names import plain
from src.api.view_models.news import news_context
from src.db.repositories.news_repo import NewsRepository


def _id():
    return str(uuid.uuid4())


@pytest.fixture
def lg(db_conn, factory):
    """A 2025 league: Josh runs the Captains, Bertie (AI) the Samurai."""
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="Amsterdam", mascot="Captains")
    theirs = factory.team(city="Tokyo", mascot="Samurai")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    ai = factory.gm(team=theirs, league=league, is_ai=True)
    db_conn.execute("UPDATE gms SET display_name = 'Josh' WHERE id = %s", (gm.id,))
    db_conn.execute("UPDATE gms SET display_name = 'Bertie' WHERE id = %s", (ai.id,))
    # The feed starts with the league: nothing played yet.
    news.update_league(db_conn, league.id)
    return {
        "league": league, "season": season, "mine": mine, "theirs": theirs,
        "gm": gm, "ai": ai, "factory": factory,
    }  # fmt: skip


def _game(db, lg, day, winner, loser, series_id=None):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed)
           VALUES (%s, %s, %s, %s, %s, %s, 5, 3, %s, 1)""",
        (gid, day, lg["season"].id, series_id, winner.id, loser.id, winner.id),
    )
    for team, won in ((winner, 1), (loser, 0)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, %s, %s, %s)",
            (gid, team.id, 5 if won else 3, won, 1 - won),
        )
    return gid


def _player(db, lg, team, first="Ruben", last="Ruiz"):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position,"
        " league_id) VALUES (%s, %s, %s, 'R', 'R', 'RF', %s)",
        (pid, first, last, lg["league"].id),
    )
    db.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (team.id, pid)
    )
    return pid


def _line(db, gid, pid, team, opp, **stats):
    cols = {"bat_ab": 4, "bat_hits": 0, "bat_doubles": 0, "bat_triples": 0,
            "bat_home_runs": 0, "bat_rbi": 0, "bat_walks": 0, **stats}  # fmt: skip
    db.execute(
        f"""INSERT INTO player_game_stats (game_id, player_id, team_id,
                opponent_team_id, {", ".join(cols)})
            VALUES (%s, %s, %s, %s, {", ".join(["%s"] * len(cols))})""",
        (gid, pid, team.id, opp.id, *cols.values()),
    )


def _season_stats(db, lg, pid, team, **stats):
    cols = ", ".join(stats)
    db.execute(
        f"""INSERT INTO player_season_stats (player_id, season_id, team_id,
                is_postseason, {cols})
            VALUES (%s, %s, %s, FALSE, {", ".join(["%s"] * len(stats))})
            ON CONFLICT (player_id, season_id, team_id, is_postseason)
            DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in stats)}""",
        (pid, lg["season"].id, team.id, *stats.values()),
    )


def _draft(db, lg, pid, team, gm, rnd=3, year=2025):
    did = _id()
    db.execute(
        "INSERT INTO drafts (id, league_id, season_id, format, state)"
        " VALUES (%s, %s, %s, 'preference', 'complete')",
        (did, lg["league"].id, lg["season"].id),
    )
    db.execute(
        """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id,
               player_id) VALUES (%s, %s, %s, %s, %s, %s)""",
        (did, rnd * 10, rnd, gm.id, team.id, pid),
    )
    return did


def _stories(db, lg, kind=None):
    rows = NewsRepository(db).feed(lg["league"].id, limit=200)
    # The text as it reads; the links are checked in TestLinks.
    for r in rows:
        r["headline"], r["body"] = plain(r["headline"]), plain(r["body"])
    return [r for r in rows if kind is None or r["kind"] == kind]


class TestStreaks:
    def test_a_winning_streak_credits_the_gm(self, db_conn, lg):
        for day in range(1, 8):
            _game(db_conn, lg, f"2025-04-0{day}", lg["mine"], lg["theirs"])

        news.update_league(db_conn, lg["league"].id)

        wins = [s for s in _stories(db_conn, lg, "streak") if "win" in s["headline"]]
        assert [s["headline"] for s in wins] == [
            "Captains win 7 straight under GM Josh"
        ]
        assert wins[0]["news_date"] == "2025-04-07"
        assert lg["mine"].id in wins[0]["team_ids"]
        assert lg["gm"].id in wins[0]["gm_ids"]

    def test_the_same_day_at_a_time_or_all_at_once(self, db_conn, lg):
        for day in range(1, 9):
            _game(db_conn, lg, f"2025-04-0{day}", lg["mine"], lg["theirs"])
            news.update_league(db_conn, lg["league"].id)
        news.update_league(db_conn, lg["league"].id)

        heads = sorted(s["headline"] for s in _stories(db_conn, lg, "streak"))
        assert heads == [
            "Captains win 7 straight under GM Josh",
            "Samurai drop 8 in a row",
        ]

    def test_a_league_already_running_skips_its_old_days(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season(year=2025)
        factory.league_season(league, season)
        a, b = (
            factory.team(city="A", mascot="Aces"),
            factory.team(city="B", mascot="Bees"),
        )
        for t in (a, b):
            factory.league_season_team(league, season, t)
        old = {"league": league, "season": season}
        for day in range(1, 8):
            _game(db_conn, old, f"2025-04-0{day}", a, b)

        news.update_league(db_conn, league.id)  # the feed's first run
        assert _stories(db_conn, old, "streak") == []

        for day in range(8, 11):
            _game(db_conn, old, f"2025-04-{day:02d}", a, b)
        news.update_league(db_conn, league.id)
        # The 8th and 10th games are new; the 7th wasn't.
        assert sorted(s["headline"] for s in _stories(db_conn, old, "streak")) == [
            "Aces win 10 straight",
            "Bees drop 8 in a row",
        ]


class TestPlayers:
    def test_a_three_homer_game_says_who_drafted_him(self, db_conn, lg):
        pid = _player(db_conn, lg, lg["mine"])
        _draft(db_conn, lg, pid, lg["mine"], lg["gm"])
        gid = _game(db_conn, lg, "2025-04-02", lg["mine"], lg["theirs"])
        _line(db_conn, gid, pid, lg["mine"], lg["theirs"], bat_hits=3,
              bat_home_runs=3, bat_rbi=5)  # fmt: skip

        news.update_league(db_conn, lg["league"].id)

        (s,) = _stories(db_conn, lg, "big_game")
        assert s["headline"] == "Ruben Ruiz hits three home runs"
        assert "Ruiz was drafted by GM Josh in 2025 (round 3)." in s["body"]
        assert pid in s["player_ids"]

    def test_a_season_milestone_is_news_once(self, db_conn, lg):
        pid = _player(db_conn, lg, lg["mine"])
        _season_stats(db_conn, lg, pid, lg["mine"], bat_home_runs=29)
        news.update_league(db_conn, lg["league"].id)
        gid = _game(db_conn, lg, "2025-08-02", lg["mine"], lg["theirs"])
        _line(db_conn, gid, pid, lg["mine"], lg["theirs"], bat_hits=1, bat_home_runs=1)
        _season_stats(db_conn, lg, pid, lg["mine"], bat_home_runs=30)

        news.update_league(db_conn, lg["league"].id)
        news.update_league(db_conn, lg["league"].id)

        assert [s["headline"] for s in _stories(db_conn, lg, "milestone")] == [
            "Ruben Ruiz reaches 30 home runs"
        ]

    def test_a_long_injury(self, db_conn, lg):
        pid = _player(db_conn, lg, lg["mine"])
        _game(db_conn, lg, "2025-05-01", lg["mine"], lg["theirs"])
        db_conn.execute(
            """INSERT INTO player_injury_log (player_id, season_id, team_id,
                   injury_date, severity, activity, games_missed)
               VALUES (%s, %s, %s, '2025-05-01', 'severe', 'fielding', 42)""",
            (pid, lg["season"].id, lg["mine"].id),
        )
        news.update_league(db_conn, lg["league"].id)
        (s,) = _stories(db_conn, lg, "injury")
        assert s["headline"] == "Captains lose Ruben Ruiz for 6 weeks"
        assert "while fielding" in s["body"]


class TestTrades:
    def _trade(self, db, lg, sent, got, on="2025-05-10"):
        oid = _id()
        db.execute(
            """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
                   to_team_id, from_gm_id, status, created_on)
               VALUES (%s, %s, %s, %s, %s, %s, 'accepted', %s)""",
            (oid, lg["league"].id, lg["season"].id, lg["mine"].id, lg["theirs"].id,
             lg["gm"].id, on),
        )  # fmt: skip
        for pid, team in ((sent, lg["mine"]), (got, lg["theirs"])):
            db.execute(
                "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)"
                " VALUES (%s, %s, %s)",
                (oid, pid, team.id),
            )
        db.execute(
            "UPDATE team_players SET team_id = %s WHERE player_id = %s",
            (lg["mine"].id, got),
        )
        db.execute(
            "UPDATE team_players SET team_id = %s WHERE player_id = %s",
            (lg["theirs"].id, sent),
        )
        return oid

    def test_a_trade_makes_the_news_with_both_sides(self, db_conn, lg):
        sent = _player(db_conn, lg, lg["mine"], "Sam", "Spare")
        got = _player(db_conn, lg, lg["theirs"], "Kai", "Kim")
        self._trade(db_conn, lg, sent, got)

        news.record_trades(db_conn, lg["league"].id)

        (s,) = _stories(db_conn, lg, "trade")
        assert s["headline"] == "GM Josh's Captains land Kai Kim from the Samurai"
        assert "the Tokyo Samurai get Sam Spare" in s["body"]

    def test_the_trade_verdict_at_season_end(self, db_conn, lg):
        sent = _player(db_conn, lg, lg["mine"], "Sam", "Spare")
        got = _player(db_conn, lg, lg["theirs"], "Kai", "Kim")
        self._trade(db_conn, lg, sent, got, on="2025-05-10")
        # Kim rakes for the Captains after the trade: 25 games, 2-for-4 each.
        for day in range(11, 31):
            gid = _game(db_conn, lg, f"2025-05-{day}", lg["mine"], lg["theirs"])
            _line(db_conn, gid, got, lg["mine"], lg["theirs"], bat_hits=2,
                  bat_home_runs=1, bat_rbi=2)  # fmt: skip
        for day in range(1, 6):
            gid = _game(db_conn, lg, f"2025-06-0{day}", lg["mine"], lg["theirs"])
            _line(db_conn, gid, got, lg["mine"], lg["theirs"], bat_hits=2,
                  bat_home_runs=1, bat_rbi=2)  # fmt: skip

        news.update_league(db_conn, lg["league"].id)

        (s,) = _stories(db_conn, lg, "verdict")
        assert s["headline"] == "GM Josh's trade for Kim pays off"
        assert s["body"].startswith("Kai Kim hit .500 with 25 HR and 50 RBI")
        assert "GM Bertie may want that one back." in s["body"]
        assert s["weight"] == 3


class TestPlayoffs:
    def test_the_champion_credits_the_gm(self, db_conn, lg):
        sid = _id()
        db_conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
            (sid, lg["season"].id),
        )
        _game(db_conn, lg, "2025-10-01", lg["theirs"], lg["mine"], sid)
        for day in range(2, 6):
            _game(db_conn, lg, f"2025-10-0{day}", lg["mine"], lg["theirs"], sid)
        # A game after it was over doesn't change the result.
        _game(db_conn, lg, "2025-10-07", lg["theirs"], lg["mine"], sid)

        news.update_league(db_conn, lg["league"].id)

        (s,) = _stories(db_conn, lg, "champion")
        assert s["headline"] == "GM Josh's Captains win the 2025 championship"
        assert "beat the Samurai 4-1 in the Finals" in s["body"]
        assert s["news_date"] == "2025-10-05"
        assert s["weight"] == 3


class TestNewsTab:
    @pytest.fixture
    def client(self, db_conn, lg):
        user_id = _id()
        db_conn.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'Josh')",
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

    def test_shows_the_stories_and_clears_the_badge(self, client, db_conn, lg):
        for day in range(1, 8):
            _game(db_conn, lg, f"2025-04-0{day}", lg["mine"], lg["theirs"])
        news.update_league(db_conn, lg["league"].id)
        repo = NewsRepository(db_conn)
        assert repo.count_unseen(lg["league"].id, lg["gm"].id) == 1

        r = client.get(f"/leagues/{lg['league'].id}/headlines")

        assert r.status_code == 200
        assert "League News" in r.text
        assert "win 7 straight under GM" in r.text
        assert repo.count_unseen(lg["league"].id, lg["gm"].id) == 0

    def test_the_badge_count(self, client, db_conn, lg):
        url = f"/leagues/{lg['league'].id}/headlines/unseen"
        assert client.get(url).json() == {"count": 0}
        for day in range(1, 8):
            _game(db_conn, lg, f"2025-04-0{day}", lg["mine"], lg["theirs"])
        news.update_league(db_conn, lg["league"].id)
        assert client.get(url).json() == {"count": 1}
        client.get(f"/leagues/{lg['league'].id}/headlines")
        assert client.get(url).json() == {"count": 0}

    def test_my_team_only(self, client, db_conn, lg):
        other = lg["factory"].team(city="Dublin", mascot="Shamrocks")
        NewsRepository(db_conn).add(
            lg["league"].id, lg["season"].id, "2025-04-01", "trade", "t1",
            "Shamrocks do a thing", weight=2, team_ids=[other.id],
        )  # fmt: skip
        NewsRepository(db_conn).add(
            lg["league"].id, lg["season"].id, "2025-04-02", "trade", "t2",
            "Captains do a thing", weight=2, team_ids=[lg["mine"].id],
        )  # fmt: skip
        r = client.get(f"/leagues/{lg['league'].id}/headlines?mine=1")
        assert "Captains do a thing" in r.text
        assert "Shamrocks do a thing" not in r.text

    def test_a_gms_profile_opens_inside_the_league(self, client, db_conn, lg):
        name = f"josh-{_id()[:8]}"
        db_conn.execute(
            """UPDATE users SET username = %s
               WHERE id = (SELECT user_id FROM gms WHERE id = %s)""",
            (name, lg["gm"].id),
        )
        url = f"/leagues/{lg['league'].id}/gms/{name}?back=headlines"

        # From a tab: just the profile, with the way back to News.
        r = client.get(url, headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert "Back to News" in r.text
        assert f"@{name}" in r.text
        # Opened directly: inside the league's page, tabs and all.
        r = client.get(url)
        assert r.status_code == 200
        assert 'id="tab-content"' in r.text
        assert "Back to News" in r.text

        assert client.get(f"/leagues/{lg['league'].id}/gms/nobody").status_code == 404

    def test_standings_shows_the_headlines(self, client, db_conn, lg):
        NewsRepository(db_conn).add(
            lg["league"].id, lg["season"].id, "2025-04-02", "trade", "t2",
            "Captains do a big thing", weight=3, team_ids=[lg["mine"].id],
        )  # fmt: skip
        r = client.get(f"/leagues/{lg['league'].id}/standings")
        assert r.status_code == 200
        assert "Captains do a big thing" in r.text


class TestLinks:
    def test_players_teams_and_gms_are_links(self, db_conn, lg):
        pid = _player(db_conn, lg, lg["mine"])
        _draft(db_conn, lg, pid, lg["mine"], lg["gm"])
        gid = _game(db_conn, lg, "2025-04-02", lg["mine"], lg["theirs"])
        _line(db_conn, gid, pid, lg["mine"], lg["theirs"], bat_hits=3,
              bat_home_runs=3, bat_rbi=5)  # fmt: skip
        news.update_league(db_conn, lg["league"].id)

        (item,) = [
            s for s in news_context(db_conn, lg["league"].id, lg["mine"].id)[
                "news_days"][0]["stories"] if s["kind"] == "big_game"
        ]  # fmt: skip

        assert f"openPlayerPanel('{pid}')" in item["headline_html"]
        assert f"stats?team_id={lg['theirs'].id}" in item["body_html"]
        # No profile or persona to go to: the name alone, after "GM".
        assert "was drafted by GM Josh in 2025" in item["body_html"]

    def test_gm_links_stay_in_the_league(self):
        from src.api.view_models.news import _link

        ai = _link("g", "g1", "Bertie", "L", {"g1": {"persona_id": "p1"}})
        assert 'hx-get="/leagues/L/personas/p1?back=headlines"' in ai
        person = _link("g", "g2", "Josh", "L", {"g2": {"username": "josh"}})
        assert 'hx-get="/leagues/L/gms/josh?back=headlines"' in person
        assert person.startswith("GM <a")

    def test_names_are_escaped(self, db_conn, lg):
        NewsRepository(db_conn).add(
            lg["league"].id, lg["season"].id, "2025-04-01", "trade", "x",
            "<b>bold</b> \u27e6t:" + lg["mine"].id + "|Captains\u27e7",
            weight=2,
        )  # fmt: skip
        (day,) = news_context(db_conn, lg["league"].id, None)["news_days"]
        html = day["stories"][0]["headline_html"]
        assert "&lt;b&gt;bold&lt;/b&gt;" in html
        assert ">Captains</a>" in html
