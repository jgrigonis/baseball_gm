# tests/api/test_all_star.py
"""All-Star voting in a league (src/api/services/all_star.py): when the ballot
is open, saving a GM's ballot, counting every team's votes at the break, the
sim stopping for it and the All-Star tab."""

import random
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
        "Votes for his own.",
        "The Homer",
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


# ── Multiplayer: the ready-check bar ─────────────────────────────────────────


def _multiplayer(lg):
    """Both teams run by people, so the league moves on by ready-check."""
    lg.db.execute("UPDATE gms SET is_ai = FALSE WHERE league_id = %s", (lg.league.id,))
    for row in lg.db.execute(
        "SELECT id FROM gms WHERE league_id = %s", (lg.league.id,)
    ).fetchall():
        lg.db.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'x')",
            (row["id"], row["id"]),
        )
        lg.db.execute("UPDATE gms SET user_id = id WHERE id = %s", (row["id"],))


def test_the_ready_bar_knows_when_voting_opens_and_closes(lg):
    from src.api.services import ready_check

    _multiplayer(lg)
    status = ready_check.status(lg.db, lg.league.id, lg.gm.id)
    assert status["all_star"] == "upcoming" and not status["all_star_vote_due"]

    _play_through(lg.db, lg.season, BEFORE[10])
    status = ready_check.status(lg.db, lg.league.id, lg.gm.id)
    assert status["all_star"] == "open" and status["all_star_vote_due"]

    ss = {"ss": [lg.players[("mine", "ss")]]}
    all_star.submit(lg.db, lg.league.id, lg.season.id, lg.mine.id, ss)
    assert not ready_check.status(lg.db, lg.league.id, lg.gm.id)["all_star_vote_due"]

    _play_through(lg.db, lg.season, CLOSES)
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    assert ready_check.status(lg.db, lg.league.id, lg.gm.id)["all_star"] == "done"


# ── The All-Star Game ────────────────────────────────────────────────────────


def _standings(lg, leader):
    """Every game before the break won by `leader`, so its GM is captain 1."""
    other = lg.theirs if leader is lg.mine else lg.mine
    for row in lg.db.execute(
        "SELECT id FROM games WHERE season_id = %s AND game_date <= %s",
        (lg.season.id, CLOSES),
    ).fetchall():
        for team, won in ((leader, 1), (other, 0)):
            lg.db.execute(
                """INSERT INTO team_game_stats (game_id, team_id, runs, hits,
                                                errors, win, loss)
                   VALUES (%s, %s, %s, 8, 0, %s, %s)""",
                (row["id"], team.id, 3 + won, won, 1 - won),
            )


def _count(lg, leader):
    _standings(lg, leader)
    _play_through(lg.db, lg.season, CLOSES)
    all_star.count_votes(lg.db, lg.league.id, lg.season.id)
    repo = AllStarRepository(lg.db)
    return repo, repo.game(lg.season.id)


def _picks(repo, lg):
    stars = repo.all_stars(lg.season.id)
    return {r["player_id"]: r["side"] for r in stars if r["side"]}


def test_the_two_best_teams_gms_are_the_captains(lg):
    repo, g = _count(lg, lg.mine)
    assert g["captain1_team_id"] == lg.mine.id
    assert g["captain2_team_id"] == lg.theirs.id
    assert g["state"] == "draft" and g["game_date"] == "2025-04-23"
    # I pick first, so the AI captain waits for me.
    assert _picks(repo, lg) == {}
    assert all_star.my_turn(lg.db, lg.league.id, lg.season.id, lg.mine.id)


def test_an_ai_captain_picks_straight_away(lg):
    repo, g = _count(lg, lg.theirs)
    assert g["captain1_team_id"] == lg.theirs.id
    assert len(_picks(repo, lg)) == 1
    assert all_star.my_turn(lg.db, lg.league.id, lg.season.id, lg.mine.id)


def test_a_pick_and_the_ai_answers(lg):
    repo, _ = _count(lg, lg.mine)
    ss = lg.players[("theirs", "ss")]
    all_star.pick(lg.db, lg.league.id, lg.season.id, lg.mine.id, ss)
    picks = _picks(repo, lg)
    # Pick 1 is mine, 2 and 3 the AI's, and it's my turn again.
    assert picks[ss] == 1 and len(picks) == 3
    assert sorted(picks.values()) == [1, 2, 2]
    with pytest.raises(ValueError, match="isn't available"):
        all_star.pick(lg.db, lg.league.id, lg.season.id, lg.mine.id, ss)
    with pytest.raises(ValueError, match="isn't your pick"):
        all_star.pick(lg.db, lg.league.id, lg.season.id, lg.theirs.id, ss)


def test_the_scouts_can_make_my_picks(lg):
    repo, _ = _count(lg, lg.mine)
    all_star.auto_draft(lg.db, lg.league.id, lg.season.id, lg.mine.id)
    picks = _picks(repo, lg)
    assert len(picks) == 24
    assert sorted(set(picks.values())) == [1, 2]
    assert not all_star.my_turn(lg.db, lg.league.id, lg.season.id, lg.mine.id)
    with pytest.raises(ValueError, match="aren't an All-Star captain"):
        all_star.auto_draft(lg.db, lg.league.id, lg.season.id, "nobody")


def _tie(lg):
    """A tie for the last spot: one pitcher left out, tied with the last one
    in."""
    out = lg.players[("theirs", "p2")]
    real = rules.select_pool

    def pool(cands, pts):
        rows = [r for r in real(cands, pts) if r["player_id"] != out]
        rows[-1]["wildcard"] = True
        rows[-1]["points"] = max(rows[-1]["points"], 1)
        return rows

    def tie(cands, pts, pool):
        return [pool[-1]["player_id"], out]

    return patch.multiple(rules, select_pool=pool, last_spot_tie=tie), out


def test_a_person_as_captain_2_breaks_the_tie(lg):
    tied, out = _tie(lg)
    with tied:
        repo, g = _count(lg, lg.theirs)
    assert g["state"] == "tie" and g["tied_ids"][1] == out
    assert len(repo.all_stars(lg.season.id)) == 22
    # Nobody drafts until it's settled.
    assert _picks(repo, lg) == {}
    assert all_star.my_turn(lg.db, lg.league.id, lg.season.id, lg.mine.id)
    with pytest.raises(ValueError, match="isn't in the tie"):
        all_star.break_tie(lg.db, lg.league.id, lg.season.id, lg.mine.id, "x")
    all_star.break_tie(lg.db, lg.league.id, lg.season.id, lg.mine.id, out)
    assert out in repo.ids(lg.season.id) and len(repo.ids(lg.season.id)) == 23
    assert repo.game(lg.season.id)["state"] == "draft"
    assert len(_picks(repo, lg)) == 1  # the AI's first pick


def test_an_ai_captain_2_leaves_the_tie_to_the_stats(lg):
    tied, out = _tie(lg)
    with tied:
        repo, g = _count(lg, lg.mine)
    assert g["state"] == "draft" and g["tied_ids"] == []
    assert out not in repo.ids(lg.season.id) and len(repo.ids(lg.season.id)) == 23


def test_the_game_is_played_after_the_break(lg):
    repo, g = _count(lg, lg.mine)
    assert not all_star.game_due(lg.db, lg.season.id, CLOSES)
    assert all_star.game_due(lg.db, lg.season.id, AFTER[0])
    result = all_star.play_game(lg.db, lg.league.id, lg.season.id, random.Random(7))
    g = repo.game(lg.season.id)
    assert g["state"] == "played" and all_star.phase(lg.db, lg.season.id) == "played"
    assert (g["score1"], g["score2"]) == (result["score1"], result["score2"])
    assert g["score1"] != g["score2"] and g["innings"] >= 9
    assert not all_star.game_due(lg.db, lg.season.id, AFTER[0])
    # The draft was finished for me, and everyone drafted played.
    lines = repo.lines(lg.season.id)
    assert len(_picks(repo, lg)) == 24
    assert {r["side"] for r in lines} == {1, 2}
    assert sum(1 for r in lines if r["batting_order"]) == 18
    # Every pitcher who pitched is on the box score, starters first. (This
    # little league is short of hitters, so some pitchers play the field:
    # tests/game/test_pitcher_outs_cap.py covers the cap.)
    for side in (1, 2):
        arms = [r for r in lines if r["side"] == side and r["pitch_order"]]
        assert sorted(r["pitch_order"] for r in arms) == list(range(1, len(arms) + 1))
    winner = 1 if g["score1"] > g["score2"] else 2
    assert (
        next(r for r in lines if r["player_id"] == g["mvp_player_id"])["side"] == winner
    )
    # It is played once.
    assert all_star.play_game(lg.db, lg.league.id, lg.season.id) is None


def test_an_unbroken_tie_goes_to_the_stats_at_game_time(lg):
    tied, out = _tie(lg)
    with tied:
        repo, g = _count(lg, lg.theirs)
    last = g["tied_ids"][0]
    all_star.play_game(lg.db, lg.league.id, lg.season.id, random.Random(3))
    assert last in repo.ids(lg.season.id) and out not in repo.ids(lg.season.id)


def test_the_sim_stops_after_the_all_star_game(lg):
    days = iter(AFTER)

    def one_day(league_id, conn):
        d = next(days)
        return {"game_date": d, "games_played": 0, "all_star_game": True}

    with patch.object(sim_next, "sim_next_day", side_effect=one_day) as day:
        summary = sim_next.sim_days(lg.league.id, lg.db, "season")
    assert day.call_count == 1 and summary["all_star_game"] is True


def test_the_sim_plays_the_all_star_game_instead_of_the_day(lg):
    _count(lg, lg.mine)
    out = sim_next.sim_next_day(lg.league.id, lg.db)
    assert out["all_star_game"] is True and out["games_played"] == 0
    assert all_star.phase(lg.db, lg.season.id) == "played"


def test_drafting_on_the_tab(client, lg):
    _count(lg, lg.mine)
    url = f"/leagues/{lg.league.id}/allstar"
    html = client.get(url).text
    assert "Pick 1 of 24" in html and "re up." in html
    assert ">Pick<" in html  # the tab badge
    ss = lg.players[("theirs", "ss")]
    origin = {"Origin": "http://testserver"}
    r = client.post(
        f"{url}/pick", data={"player_id": ss}, headers=origin, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == url
    assert "Pick 4 of 24" in client.get(url).text
    r = client.post(
        f"{url}/pick", data={"player_id": ss}, headers=origin, follow_redirects=False
    )
    assert "error=" in r.headers["location"]
    assert "isn&#39;t available" in client.get(r.headers["location"]).text
    client.post(f"{url}/auto", headers=origin)
    assert "The draft is done" in client.get(url).text


def test_the_game_on_the_tab_and_the_career_page(client, lg):
    _count(lg, lg.mine)
    all_star.play_game(lg.db, lg.league.id, lg.season.id, random.Random(11))
    g = AllStarRepository(lg.db).game(lg.season.id)
    html = client.get(f"/leagues/{lg.league.id}/allstar").text
    assert "Final" in html and "★ MVP" in html and "Team My" in html
    assert "line-score" in html and "Pitching" in html
    career = client.get(
        f"/leagues/{lg.league.id}/players/{g['mvp_player_id']}/career"
    ).text
    assert "All-Star Games" in career and "★ MVP" in career


def test_the_ready_bar_knows_its_my_pick(lg):
    from src.api.services import ready_check

    _multiplayer(lg)
    _count(lg, lg.theirs)
    status = ready_check.status(lg.db, lg.league.id, lg.gm.id)
    assert status["all_star"] == "done"
    # Both captains are people now: captain 1 (theirs) picks first.
    assert not status["all_star_turn"]
    other = lg.db.execute(
        "SELECT id FROM gms WHERE team_id = %s", (lg.theirs.id,)
    ).fetchone()["id"]
    assert ready_check.status(lg.db, lg.league.id, other)["all_star_turn"]


def _hurt(lg, player_id):
    lg.db.execute(
        """INSERT INTO player_injuries (player_id, league_id, games_remaining,
                                        return_date)
           VALUES (%s, %s, 30, '2025-12-31')""",
        (player_id, lg.league.id),
    )


def test_a_hurt_all_star_sits_out_and_a_reserve_takes_his_place(lg):
    # theirs-p2 misses the pool on the tiebreak; mine-p0 is hurt.
    tied, out = _tie(lg)
    hurt = lg.players[("mine", "p0")]
    _hurt(lg, hurt)
    with tied:
        repo, g = _count(lg, lg.mine)
    stars = {r["player_id"]: r for r in repo.all_stars(lg.season.id)}
    # Still an All-Star, with a reserve in his place.
    assert hurt in stars and stars[out]["replaces"] == hurt
    assert all_star.my_turn(lg.db, lg.league.id, lg.season.id, lg.mine.id)
    with pytest.raises(ValueError, match="isn't available"):
        all_star.pick(lg.db, lg.league.id, lg.season.id, lg.mine.id, hurt)
    all_star.play_game(lg.db, lg.league.id, lg.season.id, random.Random(5))
    picks = _picks(repo, lg)
    assert hurt not in picks and out in picks and len(picks) == 23
    played = {r["player_id"] for r in repo.lines(lg.season.id)}
    assert hurt not in played


def test_hurt_all_stars_and_reserves_on_the_tab(client, lg):
    tied, out = _tie(lg)
    hurt = lg.players[("mine", "p0")]
    _hurt(lg, hurt)
    with tied:
        _count(lg, lg.mine)
    html = client.get(f"/leagues/{lg.league.id}/allstar").text
    assert "Out hurt:" in html and 'class="as-hurt"' in html
    assert "Reserves" in html and "and 1 reserve" in html
    assert "Pick 1 of 23" in html


def test_the_date_shows_the_all_star_game_until_it_is_played(lg):
    from src.web.utils import _current_league_date

    _count(lg, lg.mine)
    assert _current_league_date(lg.db, lg.season.id, "season") == "2025-04-23"
    assert (
        _current_league_date(lg.db, lg.season.id, "season", all_star_game=False)
        == AFTER[0]
    )
    all_star.play_game(lg.db, lg.league.id, lg.season.id, random.Random(2))
    assert _current_league_date(lg.db, lg.season.id, "season") == AFTER[0]
