# tests/api/web/test_public_league_viewers.py
"""
Anyone signed in can follow a public league once it has started, without
joining: its standings, leaders, team stats, playoffs, draft results and
history. The pages built around one GM's own team stay GM-only, and so does
every action. Private leagues stay GM-only throughout, except to admins,
who can view any league once it has started.
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.view_models.standings import standings_context


@pytest.fixture
def user_id(db_conn):
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username, password_hash)"
        " VALUES (%s, %s, 'Viewer', %s, 'x')",
        (uid, uid, uid),
    )
    return uid


def _client(db_conn, user_id, is_admin=False):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user_id,
        "has_password": True,
        "display_name": "Viewer",
        "is_admin": is_admin,
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.fixture
def client(db_conn, user_id):
    yield from _client(db_conn, user_id)


@pytest.fixture
def admin_client(db_conn, user_id):
    yield from _client(db_conn, user_id, is_admin=True)


def _league(db, factory, state="season", is_public=True):
    """A league in its 2025 season with two teams, one of them run by a GM
    who isn't the viewer."""
    league = factory.league(state=state)
    db.execute(
        "UPDATE leagues SET is_public = %s WHERE id = %s", (is_public, league.id)
    )
    season = factory.season(year=2025)
    factory.league_season(league, season)
    home = factory.team(city="Boston", mascot="Beans")
    away = factory.team(city="Chicago", mascot="Wind")
    for team in (home, away):
        factory.league_season_team(league, season, team)
    factory.gm(team=home, league=league, is_ai=False)
    factory.gm(team=away, league=league)
    db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               home_score, away_score, winner_id, completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 5, 3, %s, 1)""",
        (str(uuid.uuid4()), season.id, home.id, away.id, home.id),
    )
    return league, home


VIEWABLE = [
    "standings",
    "leaders",
    "stats",
    "playoffs",
    "history",
    "season-summary",
    "retirement",
    "draft/results",
    "league",
]
GM_ONLY = ["schedule", "roster", "lineup", "strategy", "draft"]


@pytest.mark.parametrize("page", VIEWABLE)
def test_viewer_sees_league_pages(client, db_conn, factory, page):
    league, _ = _league(db_conn, factory)

    r = client.get(f"/leagues/{league.id}/{page}")

    assert r.status_code == 200
    assert "Viewing" in r.text


@pytest.mark.parametrize("page", GM_ONLY)
def test_viewer_cant_open_gm_pages(client, db_conn, factory, page):
    league, _ = _league(db_conn, factory)

    r = client.get(f"/leagues/{league.id}/{page}", headers={"accept": "text/html"})

    assert r.status_code == 303
    assert r.headers["location"] == "/leagues/"


def test_viewer_tabs_leave_out_gm_pages(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    tabs = html.split('id="tab-bar"')[1].split("</nav>")[0]
    for tab in ("standings", "leaders", "stats"):
        assert f'hx-get="/leagues/{league.id}/{tab}"' in tabs
    for tab in GM_ONLY:
        assert f'hx-get="/leagues/{league.id}/{tab}"' not in tabs


def test_viewer_gets_no_sim_controls(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert "Play Day" not in html
    assert "/news`" not in html


def test_viewer_page_follows_the_league(client, db_conn, factory):
    """With no ready bar, a viewer's page polls /progress to refresh the open
    tab once the league moves on."""
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert "/progress')" in html
    assert 'id="ready-bar"' not in html


def test_viewer_reads_league_progress(client, db_conn, factory):
    league, _ = _league(db_conn, factory)
    db_conn.execute("UPDATE leagues SET sim_period = 4 WHERE id = %s", (league.id,))

    r = client.get(f"/leagues/{league.id}/progress")

    assert r.status_code == 200
    assert r.json() == {"state": "season", "sim_period": 4, "games_played": 1}


def test_private_league_progress_stays_closed(client, db_conn, factory):
    league, _ = _league(db_conn, factory, is_public=False)

    assert client.get(f"/leagues/{league.id}/progress").status_code == 403


def test_standings_link_each_team_to_its_roster(client, db_conn, factory):
    league, home = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert f"/leagues/{league.id}/stats?team_id={home.id}" in html


def test_viewer_stats_start_on_a_team(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/stats").text

    assert "selected" in html.split('id="team-select"')[1].split("</select>")[0]


def _team_game(db, game_id, winner, loser):
    for team, won in ((winner, 1), (loser, 0)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, 0, %s, %s)",
            (game_id, team, won, 1 - won),
        )


def test_stats_header_shows_the_teams_record(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT id, season_id, away_team_id FROM games WHERE home_team_id = %s",
        (home.id,),
    ).fetchone()
    _team_game(db_conn, game["id"], home.id, game["away_team_id"])
    series_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Final')",
        (series_id, game["season_id"]),
    )
    for _ in range(2):
        playoff_id = str(uuid.uuid4())
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, series_id,
                   home_team_id, away_team_id, home_score, away_score,
                   winner_id, completed)
               VALUES (%s, '2025-10-01', %s, %s, %s, %s, 1, 4, %s, 1)""",
            (
                playoff_id,
                game["season_id"],
                series_id,
                home.id,
                game["away_team_id"],
                game["away_team_id"],
            ),
        )
        _team_game(db_conn, playoff_id, game["away_team_id"], home.id)

    url = f"/leagues/{league.id}/stats?team_id={home.id}"
    assert "1W-0L" in client.get(url).text
    assert "0W-2L" in client.get(url + "&postseason=1").text


def test_viewer_cant_sim(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    r = client.post(f"/leagues/{league.id}/sim", json={"count": 1})

    assert r.status_code == 403


@pytest.mark.parametrize(
    "state, page", [("season", "standings"), ("complete", "history")]
)
def test_league_link_sends_viewer_to_a_viewable_page(
    client, db_conn, factory, state, page
):
    league, _ = _league(db_conn, factory, state=state)

    r = client.get(f"/leagues/{league.id}/")

    assert r.headers["location"] == f"/leagues/{league.id}/{page}"


@pytest.mark.parametrize("state, is_public", [("season", False), ("lobby", True)])
def test_private_and_lobby_leagues_stay_closed(
    client, db_conn, factory, state, is_public
):
    league, _ = _league(db_conn, factory, state=state, is_public=is_public)

    r = client.get(f"/leagues/{league.id}/standings", headers={"accept": "text/html"})

    assert r.headers["location"] == "/leagues/"


@pytest.mark.parametrize("page", VIEWABLE)
def test_admin_views_private_league(admin_client, db_conn, factory, page):
    league, _ = _league(db_conn, factory, is_public=False)

    r = admin_client.get(f"/leagues/{league.id}/{page}")

    assert r.status_code == 200
    assert "Viewing" in r.text


def test_admin_still_cant_act_in_private_league(admin_client, db_conn, factory):
    league, _ = _league(db_conn, factory, is_public=False)

    assert (
        admin_client.post(f"/leagues/{league.id}/sim", json={"count": 1}).status_code
        == 403
    )
    r = admin_client.get(
        f"/leagues/{league.id}/roster", headers={"accept": "text/html"}
    )
    assert r.headers["location"] == "/leagues/"


def test_admin_cant_view_private_lobby(admin_client, db_conn, factory):
    league, _ = _league(db_conn, factory, state="lobby", is_public=False)

    r = admin_client.get(
        f"/leagues/{league.id}/standings", headers={"accept": "text/html"}
    )

    assert r.headers["location"] == "/leagues/"


# ── Ids and exact ratings: admins only ────────────────────────────────────────


def test_admin_sees_ids_and_exact_ratings_in_player_panel(
    admin_client, db_conn, factory
):
    league, home = _league(db_conn, factory)
    player = factory.rated_player(home, league, level=61)

    html = admin_client.get(f"/leagues/{league.id}/players/{player.id}/panel").text

    assert player.id in html
    assert f'title="team_id: {home.id}"' in html
    assert '<span class="admin-value">61</span>' in html


def test_viewer_sees_no_ids_or_exact_ratings_in_player_panel(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    player = factory.rated_player(home, league, level=61)

    html = client.get(f"/leagues/{league.id}/players/{player.id}/panel").text

    assert "team_id: " not in html
    assert "admin-value" not in html
    assert "admin-id" not in html


def test_admin_sees_team_ids_in_standings(admin_client, db_conn, factory):
    league, home = _league(db_conn, factory)

    html = admin_client.get(f"/leagues/{league.id}/standings").text

    assert f"team_id: {home.id}" in html


def test_viewer_sees_no_team_ids_in_standings(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    assert "team_id: " not in client.get(f"/leagues/{league.id}/standings").text


def test_standings_show_team_badges(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert html.count('class="team-badge') == 2
    # Phones drop the city and show the nickname
    assert '>BOS</span><span class="phone-hide">Boston </span>Beans' in html


def test_game_panel_shows_both_team_badges(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    game_id = db_conn.execute(
        "SELECT id FROM games WHERE home_team_id = %s", (home.id,)
    ).fetchone()["id"]

    html = client.get(f"/leagues/{league.id}/games/{game_id}/panel").text

    assert ">CHI</span>Chicago Wind" in html
    assert ">BOS</span>Boston Beans" in html


def test_game_panel_links_each_team_to_its_season_stats(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT id, season_id, away_team_id FROM games WHERE home_team_id = %s",
        (home.id,),
    ).fetchone()

    html = client.get(f"/leagues/{league.id}/games/{game['id']}/panel").text

    header = html.split('id="game-panel-body-inner"')[0]
    for team_id in (home.id, game["away_team_id"]):
        assert (
            f"/leagues/{league.id}/stats?team_id={team_id}"
            f"&season_id={game['season_id']}"
        ) in header


def test_game_panel_calls_out_standout_performances(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT id, away_team_id FROM games WHERE home_team_id = %s", (home.id,)
    ).fetchone()
    cycler = factory.rated_player(home, league, name="Cycler")
    ace = factory.rated_player(home, league, name="Ace", pitcher=True)
    db_conn.execute(
        """INSERT INTO player_game_stats (player_id, game_id, team_id,
               opponent_team_id, bat_ab, bat_hits, bat_doubles, bat_triples,
               bat_home_runs, bat_rbi, bat_runs, bat_walks, bat_strike_outs)
           VALUES (%s, %s, %s, %s, 5, 4, 1, 1, 1, 3, 2, 0, 0)""",
        (cycler.id, game["id"], home.id, game["away_team_id"]),
    )
    db_conn.execute(
        """INSERT INTO player_game_stats (player_id, game_id, team_id,
               opponent_team_id, pitch_game_played, pitch_game_started,
               pitch_outs, pitch_hits, pitch_runs, pitch_earned_runs,
               pitch_walks, pitch_strike_outs, pitch_home_runs)
           VALUES (%s, %s, %s, %s, 1, 1, 21, 5, 3, 3, 1, 11, 0)""",
        (ace.id, game["id"], home.id, game["away_team_id"]),
    )

    html = client.get(f"/leagues/{league.id}/games/{game['id']}/panel").text

    assert "Cycler hits for the cycle as the Beans beat the Wind, 5-3" in html
    strip = html[html.index('class="standouts"') :]
    assert strip.index(">Cycle<") < strip.index(">11 K<")
    assert "4-for-5, 2B, 3B, HR, 3 RBI" in strip
    assert html.count('class="standout-row"') == 2
    assert 'title="Cycle · 4 hits"' in html


def _batting_line(html: str, name: str) -> dict[str, str]:
    """The box score line for one batter, keyed by column header."""
    row_at = html.index(name)
    table = html[html.rindex("<table", 0, row_at) : row_at]
    headers = re.findall(r"<th[^>]*>([^<]*)</th>", table)
    row = html[row_at : html.index("</tr>", row_at)]
    cells = re.findall(r'font-family:var\(--font-mono\);[^"]*">([^<]*)</td>', row)
    return dict(zip(headers[1:], cells))


def test_game_panel_box_score_shows_hit_by_pitch(client, db_conn, factory):
    """A batter who scores after a hit by pitch has a visible way on base."""
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT id, away_team_id FROM games WHERE home_team_id = %s", (home.id,)
    ).fetchone()
    plunked = factory.rated_player(home, league, name="Plunked")
    db_conn.execute(
        """INSERT INTO player_game_stats (player_id, game_id, team_id,
               opponent_team_id, bat_ab, bat_hits, bat_home_runs, bat_runs,
               bat_walks, bat_strike_outs, bat_hbp)
           VALUES (%s, %s, %s, %s, 3, 0, 0, 1, 0, 0, 1)""",
        (plunked.id, game["id"], home.id, game["away_team_id"]),
    )

    html = client.get(f"/leagues/{league.id}/games/{game['id']}/panel").text

    assert 'title="Hit by pitch">HBP</th>' in html
    line = _batting_line(html, "Plunked")
    assert (line["AB"], line["R"], line["H"], line["HBP"]) == ("3", "1", "0", "1")


def test_game_panel_box_score_drops_columns_nobody_used(client, db_conn, factory):
    """AB, R and H always show; a column like 3B shows only when someone has one."""
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT id, away_team_id FROM games WHERE home_team_id = %s", (home.id,)
    ).fetchone()
    for name, ab, hits, hr, k in (("Slugger", 4, 1, 1, 0), ("Whiffer", 4, 0, 0, 3)):
        player = factory.rated_player(home, league, name=name)
        db_conn.execute(
            """INSERT INTO player_game_stats (player_id, game_id, team_id,
                   opponent_team_id, bat_ab, bat_hits, bat_home_runs, bat_rbi,
                   bat_runs, bat_walks, bat_strike_outs)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)""",
            (
                player.id,
                game["id"],
                home.id,
                game["away_team_id"],
                ab,
                hits,
                hr,
                hr,
                hr,
                k,
            ),
        )

    html = client.get(f"/leagues/{league.id}/games/{game['id']}/panel").text

    assert list(_batting_line(html, "Slugger")) == ["AB", "R", "H", "HR", "RBI", "K"]
    assert _batting_line(html, "Slugger")["HR"] == "1"
    assert _batting_line(html, "Whiffer") == {
        "AB": "4",
        "R": "0",
        "H": "0",
        "HR": "",
        "RBI": "",
        "K": "3",
    }


def test_up_next_links_each_opponent_to_its_stats(db_conn, factory):
    league, home = _league(db_conn, factory)
    game = db_conn.execute(
        "SELECT season_id, away_team_id FROM games WHERE home_team_id = %s",
        (home.id,),
    ).fetchone()
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               completed)
           VALUES (%s, '2025-04-02', %s, %s, %s, 0)""",
        (str(uuid.uuid4()), game["season_id"], game["away_team_id"], home.id),
    )

    ctx = standings_context(db_conn, league.id, game["season_id"], home.id)

    assert [g["opp_id"] for g in ctx["upcoming"]] == [game["away_team_id"]]


def test_game_panel_shows_the_line_score_and_a_headline(client, db_conn, factory):
    league, home = _league(db_conn, factory)
    game_id = db_conn.execute(
        "SELECT id FROM games WHERE home_team_id = %s", (home.id,)
    ).fetchone()["id"]
    db_conn.execute(
        """UPDATE games SET innings_played = 9,
               line_score = '{"away": [0, 0, 3], "home": [2, 0, 0, 0, 0, 0, 0, 3]}'
           WHERE id = %s""",
        (game_id,),
    )

    html = client.get(f"/leagues/{league.id}/games/{game_id}/panel").text

    board = html.split('class="scoreboard"')[1].split('class="scoreboard-notes"')[0]
    assert "Beans beat the Wind, 5-3" in board
    # Boston led after the top of the ninth, so it didn't bat: an X
    assert '<td class="tile">3</td><td class="tile">X</td>' in board
    assert '<td class="tile rhe rhe-start">5</td>' in board
