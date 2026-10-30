# tests/api/test_all_star.py
"""All-Star voting in a league (src/api/services/all_star.py): when the ballot
is open, saving a GM's ballot, counting every team's votes at the break, the
sim stopping for it and the All-Star tab."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import all_star, sim_next
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.league import all_star as rules
from src.league import personas
from src.league.all_star import FIELD_SLOTS

# 20 game days, a 4-day break, then 6 more. The ballot closes after the games
# of the 20th day and opens 14 days before that.
START = date(2025, 4, 1)
BEFORE = [(START + timedelta(days=i)).isoformat() for i in range(20)]
AFTER = [(START + timedelta(days=24 + i)).isoformat() for i in range(6)]
OPENS, CLOSES = BEFORE[6], BEFORE[19]


def _play_through(db, season, last_day):
    db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s AND game_date <= %s",
        (season.id, last_day),
    )


@pytest.fixture
def lg(db_conn, factory):
    """Two teams, mine (a person's) and an AI team with a persona, each with a
    hitter who has started every game at each position and three pitchers,
    playing each other every day."""
    db = db_conn
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine, theirs = factory.team(city="My", mascot="Team"), factory.team()
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    ai = factory.gm(team=theirs, league=league, is_ai=True)
    persona = PersonaRepository(db).create(
        f"Homer {league.id}",
        "",
        "",
        personas.clean({"loyalty": 100, "analytics": 80}),
        # Never picked for other leagues: the sim test commits, so this
        # persona outlives the test and the lobby tests would draw it.
        0,
    )
    db.execute("UPDATE gms SET persona_id = %s WHERE id = %s", (persona, ai.id))

    games = []
    for day in BEFORE + AFTER:
        gid = factory._id()
        db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, 0)""",
            (gid, day, season.id, mine.id, theirs.id),
        )
        if day in BEFORE:
            games.append(gid)

    players = {}
    for t, tag in ((mine, "mine"), (theirs, "theirs")):
        for order, pos in enumerate(FIELD_SLOTS + ("dh",), 1):
            p = factory.rated_player(t, league, level=40 + order, name=f"{tag}-{pos}")
            players[(tag, pos)] = p.id
            for gid in games:
                db.execute(
                    """INSERT INTO game_lineup_slots
                           (game_id, team_id, player_id, position, batting_order)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (gid, t.id, p.id, pos, order),
                )
            db.execute(
                """INSERT INTO player_season_stats
                       (player_id, season_id, team_id, bat_games_played, bat_ab,
                        bat_hits, bat_home_runs, bat_rbi)
                   VALUES (%s, %s, %s, 20, 80, %s, %s, %s)""",
                (p.id, season.id, t.id, 15 + order, order, 2 * order),
            )
        for i in range(3):
            p = factory.rated_player(t, league, pitcher=True, name=f"{tag}-p{i}")
            players[(tag, f"p{i}")] = p.id
            db.execute(
                """INSERT INTO player_season_stats
                       (player_id, season_id, team_id, pitch_games_played,
                        pitch_games_started, pitch_outs, pitch_wins,
                        pitch_strike_outs, pitch_earned_runs)
                   VALUES (%s, %s, %s, 7, 7, 120, %s, %s, 10)""",
                (p.id, season.id, t.id, i, 20 + i),
            )
    return SimpleNamespace(
        db=db,
        league=league,
        season=season,
        mine=mine,
        theirs=theirs,
        gm=gm,
        players=players,
    )


def test_the_window_comes_from_the_break(lg):
    w = all_star.window(lg.db, lg.season.id)
    assert (w.opens, w.closes, w.resumes) == (OPENS, CLOSES, AFTER[0])


def test_the_phase_follows_the_calendar(lg):
    assert all_star.phase(lg.db, lg.season.id) == "upcoming"
    _play_through(lg.db, lg.season, BEFORE[5])
    assert all_star.phase(lg.db, lg.season.id) == "open"
    _play_through(lg.db, lg.season, CLOSES)
    # Past the close with no count: nothing to show.
    assert all_star.phase(lg.db, lg.season.id) == "none"
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    assert all_star.phase(lg.db, lg.season.id) == "done"


def test_players_are_on_the_ballot_where_they_started(lg):
    _play_through(lg.db, lg.season, BEFORE[10])
    cands = all_star.candidates(lg.db, lg.league.id, lg.season.id)
    slots = {c["player_id"]: c["slot"] for c in cands}
    assert slots[lg.players[("mine", "ss")]] == "ss"
    assert slots[lg.players[("theirs", "dh")]] == "dh"
    assert slots[lg.players[("mine", "p0")]] == "p"
    assert len(cands) == 2 * 12


def test_a_gm_can_save_a_ballot_only_while_it_is_open(lg):
    raw = {"ss": [lg.players[("theirs", "ss")], lg.players[("mine", "ss")]]}
    with pytest.raises(ValueError):
        all_star.submit(lg.db, lg.league.id, lg.season.id, lg.mine.id, raw)
    _play_through(lg.db, lg.season, BEFORE[10])
    all_star.submit(lg.db, lg.league.id, lg.season.id, lg.mine.id, raw)
    saved = AllStarRepository(lg.db).ballot(lg.season.id, lg.mine.id)
    assert saved["ss"] == raw["ss"]
    assert "c" not in saved  # left blank


def test_counting_the_votes(lg):
    _play_through(lg.db, lg.season, BEFORE[10])
    my_ss, their_ss = lg.players[("mine", "ss")], lg.players[("theirs", "ss")]
    all_star.submit(lg.db, lg.league.id, lg.season.id, lg.mine.id, {"ss": [my_ss]})
    _play_through(lg.db, lg.season, CLOSES)
    pool = all_star.count_votes(lg.db, lg.league.id, lg.season.id)

    repo = AllStarRepository(lg.db)
    ballots = repo.ballots(lg.season.id)
    # The AI team voted, by its persona: a homer picks his own shortstop.
    assert ballots[lg.theirs.id]["ss"][0] == their_ss
    assert len(ballots[lg.theirs.id]["p"]) == 6  # everyone there is
    # My saved ballot counted as I left it.
    assert ballots[lg.mine.id] == {"ss": [my_ss]}
    # Two teams of 12: everyone makes it.
    assert len(pool) == 24
    points = {r["player_id"]: r["points"] for r in repo.all_stars(lg.season.id)}
    # Mine: my 1st choice (2) and their 2nd (1). Theirs: their 1st.
    assert points[my_ss] == 3 and points[their_ss] == 2
    # Counting again does nothing.
    assert all_star.count_votes(lg.db, lg.league.id, lg.season.id) == []


def test_a_person_who_never_votes_gets_the_stat_ballot(lg):
    _play_through(lg.db, lg.season, CLOSES)
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    ballots = AllStarRepository(lg.db).ballots(lg.season.id)
    cands = all_star.candidates(lg.db, lg.league.id, lg.season.id)
    assert ballots[lg.mine.id] == {
        s: picks for s, picks in rules.ballot(cands).items() if picks
    }


def test_after_the_day_the_ballot_opens(lg):
    _play_through(lg.db, lg.season, BEFORE[5])
    flags = all_star.after_day(lg.db, lg.league.id, lg.season.id, BEFORE[5])
    assert flags == {"all_star_voting": True, "all_stars": False}
    _play_through(lg.db, lg.season, BEFORE[6])
    flags = all_star.after_day(lg.db, lg.league.id, lg.season.id, BEFORE[6])
    assert flags == {"all_star_voting": False, "all_stars": False}


def test_after_the_last_day_before_the_break_the_votes_are_counted(lg):
    _play_through(lg.db, lg.season, CLOSES)
    flags = all_star.after_day(lg.db, lg.league.id, lg.season.id, CLOSES)
    assert flags == {"all_star_voting": False, "all_stars": True}
    assert AllStarRepository(lg.db).has_all_stars(lg.season.id)


def test_a_season_without_a_break_has_no_vote(db_conn, factory):
    season = factory.season()
    game = factory.game_with_teams(season=season)
    flags = all_star.after_day(db_conn, "x", season.id, "2025-04-01")
    assert flags == {"all_star_voting": False, "all_stars": False}
    assert game and all_star.phase(db_conn, season.id) == "none"


def test_the_sim_stops_when_the_all_stars_are_in(lg):
    days = iter(BEFORE[17:])

    def one_day(league_id, conn):
        d = next(days)
        _play_through(conn, lg.season, d)
        return {
            "game_date": d,
            "games_played": 1,
            "all_star_voting": False,
            "all_stars": d == CLOSES,
        }

    with patch.object(sim_next, "sim_next_day", side_effect=one_day) as day:
        summary = sim_next.sim_days(lg.league.id, lg.db, "season")
    assert day.call_count == 3
    assert summary["all_stars"] is True and summary["all_star_voting"] is False


# ── The tab ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(lg):
    user = {"id": "u1", "display_name": "Me", "is_admin": False}
    gm = {"id": lg.gm.id, "team_id": lg.mine.id, "display_name": "Me"}
    app.dependency_overrides[get_db] = lambda: lg.db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: gm
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_no_tab_before_the_ballot_opens(client, lg):
    html = client.get(f"/leagues/{lg.league.id}/standings").text
    assert f'hx-get="/leagues/{lg.league.id}/allstar"' not in html
    assert "standings" in html


def test_the_ballot_starts_with_the_stat_picks(client, lg):
    _play_through(lg.db, lg.season, BEFORE[10])
    html = client.get(f"/leagues/{lg.league.id}/allstar").text
    assert f'hx-get="/leagues/{lg.league.id}/allstar"' in html and ">Vote<" in html
    assert (
        "Your ballot isn&#39;t saved yet" in html
        or "Your ballot isn't saved yet" in html
    )
    assert 'name="ss_1"' in html and 'name="p_9"' in html


def test_saving_a_ballot(client, lg):
    _play_through(lg.db, lg.season, BEFORE[10])
    my_ss = lg.players[("mine", "ss")]
    r = client.post(
        f"/leagues/{lg.league.id}/allstar/ballot",
        data={"ss_1": my_ss, "c_1": "not-a-player"},
        headers={"Origin": "http://testserver"},
    )
    assert "Ballot saved" in r.text
    assert AllStarRepository(lg.db).ballot(lg.season.id, lg.mine.id) == {"ss": [my_ss]}
    html = client.get(f"/leagues/{lg.league.id}/allstar").text
    assert "Your ballot is saved" in html and ">Vote<" not in html


def test_saving_after_the_close_is_refused(client, lg):
    _play_through(lg.db, lg.season, CLOSES)
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    r = client.post(
        f"/leagues/{lg.league.id}/allstar/ballot",
        data={"ss_1": lg.players[("mine", "ss")]},
        headers={"Origin": "http://testserver"},
    )
    assert "isn&#39;t open" in r.text or "isn't open" in r.text


def test_the_all_stars_get_a_star(client, lg):
    _play_through(lg.db, lg.season, CLOSES)
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    html = client.get(f"/leagues/{lg.league.id}/allstar").text
    assert "24 players" in html
    assert 'class="all-star-tag"' in html
    pid = lg.players[("mine", "ss")]
    panel = client.get(f"/leagues/{lg.league.id}/players/{pid}/panel").text
    assert "badge-all-star" in panel and "All-Star 2025" in panel
    career = client.get(f"/leagues/{lg.league.id}/players/{pid}/career").text
    assert "★ All-Star 2025" in career
