# tests/api/test_records_play.py
"""The stored records (src/api/services/records/play.py, replay.py):
single games and streaks kept as games are played, the backstory replayed
into games, league marks, record news, and the views built on them
(postseason, GMs, record watch, the player badge)."""

import random
import uuid

import numpy as np
import pytest

from src.api.services import records
from src.api.services.records import defs, held, play, replay, watch
from src.api.services.records.defs import BREAK, EXTEND, SKIP, Run


def _id():
    return str(uuid.uuid4())


def _player(db, league, last):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, 'Test', %s, 'R', 'R', 'of', %s)",
        (pid, last, league.id),
    )
    return pid


def _game(db, season, home, away, date, hs=5, as_=3, series_id=None):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed, innings_played)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 9)""",
        (gid, date, season.id, series_id, home.id, away.id, hs, as_,
         home.id if hs > as_ else away.id),
    )  # fmt: skip
    for team, runs, won in ((home, hs, hs > as_), (away, as_, as_ > hs)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, %s, %s, %s)",
            (gid, team.id, runs, int(won), int(not won)),
        )
    return gid


def _box(db, gid, pid, team, opp, **cols):
    cols = {"bat_ab": 4, "bat_hits": 0, **cols}
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    db.execute(
        f"""INSERT INTO player_game_stats (game_id, player_id, team_id,
                opponent_team_id, {names}) VALUES (%s, %s, %s, %s, {marks})""",
        (gid, pid, team.id, opp.id, *cols.values()),
    )


@pytest.fixture
def lg(db_conn, factory):
    """No backstory; 2030 being played. Two clubs."""
    db = db_conn
    league = factory.league(state="season")
    a = factory.team(city="Tokyo", mascot="Samurai")
    b = factory.team(city="Lagos", mascot="Leopards")
    s = factory.season(year=2030)
    factory.league_season(league, s)
    for t in (a, b):
        factory.league_season_team(league, s, t)
    # An unplayed game keeps the season going.
    db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id, completed)
           VALUES (%s, '2030-09-30', %s, %s, %s, 0)""",
        (_id(), s.id, a.id, b.id),
    )
    play.update_league(db, league.id)  # the first, quiet catch-up
    return {"league": league, "a": a, "b": b, "s": s}


def _feats(db, league_id, kind, stat):
    return db.execute(
        """SELECT * FROM record_feats WHERE league_id = %s AND kind = %s AND stat = %s
           ORDER BY value DESC""",
        (league_id, kind, stat),
    ).fetchall()


def _news(db, league_id):
    return [
        r["headline"]
        for r in db.execute(
            "SELECT headline FROM league_news WHERE league_id = %s AND kind = 'record'",
            (league_id,),
        ).fetchall()
    ]


# ── Streak rules ──────────────────────────────────────────────────────────────


def test_hitting_streak_conventions():
    g = {"ab": 0, "h": 0, "hr": 0, "bb": 2, "hbp": 0, "sf": 0}
    assert defs.hitter_outcomes(g) == {"hit": SKIP, "hr": BREAK, "onbase": EXTEND}
    g = {"ab": 0, "h": 0, "hr": 0, "bb": 0, "hbp": 0, "sf": 1}
    assert defs.hitter_outcomes(g)["hit"] == BREAK
    g = {"ab": 0, "h": 0, "hr": 0, "bb": 0, "hbp": 0, "sf": 0}  # pinch runner
    assert set(defs.hitter_outcomes(g).values()) == {SKIP}
    assert defs.pitcher_outcome(0, 0) == SKIP


def test_a_run_counts_and_ends():
    run = Run()
    run.feed(EXTEND, "d1", "g1")
    run.feed(SKIP, "d2", "g2")
    run.feed(EXTEND, "d3", "g3")
    ended = run.feed(BREAK, "d4", "g4")
    assert (ended.length, ended.start, ended.last) == (2, "d1", "d3")
    assert run.length == 0


# ── Playing games ─────────────────────────────────────────────────────────────


def test_a_big_game_beats_the_league_mark_and_makes_news(db_conn, lg):
    db = db_conn
    lid = lg["league"].id
    p = _player(db, lg["league"], "Hitter")
    q = _player(db, lg["league"], "Tied")
    g1 = _game(db, lg["s"], lg["a"], lg["b"], "2030-04-01")
    _box(db, g1, q, lg["b"], lg["a"], bat_ab=5, bat_hits=5)  # ties the mark of 5
    g2 = _game(db, lg["s"], lg["a"], lg["b"], "2030-04-02")
    _box(db, g2, p, lg["a"], lg["b"], bat_ab=6, bat_hits=6)

    play.update_league(db, lid)

    hits = _feats(db, lid, "game", "H")
    assert [(f["player_id"], f["value"]) for f in hits] == [(p, 6), (q, 5)]
    assert any("sets a league record with 6 hits" in h for h in _news(db, lid))
    game = records.book(db, lid, "game", None, lg["a"].id)
    card = next(c for _, cs in game["rec_sections"] for c in cs if c.label == "Hits")
    assert card.holders[0]["player_id"] == p and card.holders[0]["is_mine"]


def test_below_the_mark_the_card_shows_the_mark(db_conn, lg):
    db = db_conn
    lid = lg["league"].id
    p = _player(db, lg["league"], "Ok")
    g = _game(db, lg["s"], lg["a"], lg["b"], "2030-04-01")
    _box(db, g, p, lg["a"], lg["b"], bat_ab=4, bat_hits=4)
    play.update_league(db, lid)
    ctx = records.book(db, lid, "game", None, None)
    card = next(c for _, cs in ctx["rec_sections"] for c in cs if c.label == "Hits")
    assert card.mark and card.mark["shown"] == "5"
    assert [r["player_id"] for r in card.rows] == [p]
    assert _news(db, lid) == []


def test_hitting_streak_goes_on_across_runs_and_ends_with_the_season(db_conn, lg):
    db = db_conn
    lid = lg["league"].id
    p = _player(db, lg["league"], "Streaky")
    for day in range(1, 13):
        g = _game(db, lg["s"], lg["a"], lg["b"], f"2030-05-{day:02d}")
        if day == 6:  # walks only: the streak goes on
            _box(db, g, p, lg["a"], lg["b"], bat_ab=0, bat_walks=3)
        else:
            _box(db, g, p, lg["a"], lg["b"], bat_hits=1)
        if day in (4, 12):  # read in two batches
            play.update_league(db, lid)
    streak = _feats(db, lid, "streak", "hit")
    assert len(streak) == 1
    assert (streak[0]["value"], streak[0]["active"]) == (11, True)
    assert streak[0]["start_date"] == "2030-05-01"

    g = _game(db, lg["s"], lg["a"], lg["b"], "2030-05-13")
    _box(db, g, p, lg["a"], lg["b"], bat_ab=4, bat_hits=0)
    db.execute(
        "DELETE FROM games WHERE completed = 0 AND season_id = %s", (lg["s"].id,)
    )
    play.update_league(db, lid)
    streak = _feats(db, lid, "streak", "hit")
    assert (streak[0]["value"], streak[0]["active"]) == (11, False)


def test_club_winning_streak(db_conn, lg):
    db = db_conn
    lid = lg["league"].id
    for day in range(1, 8):
        _game(db, lg["s"], lg["a"], lg["b"], f"2030-06-{day:02d}")
    play.update_league(db, lid)
    win = _feats(db, lid, "streak", "twin")
    loss = _feats(db, lid, "streak", "tloss")
    assert win[0]["team_id"] == lg["a"].id and win[0]["value"] == 7
    assert loss[0]["team_id"] == lg["b"].id and loss[0]["value"] == 7


# ── The backstory replay ──────────────────────────────────────────────────────


def test_a_dealt_season_adds_up_to_the_line():
    ln = {
        "bat_games_played": 150, "bat_ab": 600, "bat_hits": 180, "bat_doubles": 35,
        "bat_triples": 4, "bat_home_runs": 40, "bat_walks": 70, "bat_hbp": 5,
        "bat_sac_flys": 5, "bat_strike_outs": 120, "bat_runs": 110, "bat_rbi": 120,
        "bat_stolen_bases": 20,
    }  # fmt: skip
    g = replay._hitter_games(ln, 162, np.random.default_rng(1))
    assert len(g["idx"]) == 150
    for stat, col in (("H", "bat_hits"), ("HR", "bat_home_runs"), ("2B", "bat_doubles"),
                      ("BB", "bat_walks"), ("K", "bat_strike_outs"), ("R", "bat_runs"),
                      ("RBI", "bat_rbi"), ("SB", "bat_stolen_bases")):  # fmt: skip
        assert g[stat].sum() == ln[col], stat
    assert (g["AB"] + g["BB"] + g["HBP"] + g["SF"]).max() <= replay.MAX_PA_PER_GAME + 1
    assert (g["H"] <= g["AB"]).all()


def test_backstory_seeds_games_and_streaks(db_conn, factory):
    db = db_conn
    league = factory.league(state="draft")
    a = factory.team(city="Tokyo", mascot="Samurai")
    b = factory.team(city="Lagos", mascot="Leopards")
    s = factory.season(year=2029)
    db.execute("UPDATE seasons SET is_backstory = TRUE WHERE id = %s", (s.id,))
    factory.league_season(league, s)
    for day in range(1, 31):
        _game(db, s, a, b, f"2029-05-{day:02d}")
    p = _player(db, league, "Slugger")
    db.execute(
        """INSERT INTO player_season_stats (player_id, season_id, team_id,
               bat_games_played, bat_ab, bat_hits, bat_home_runs, bat_runs, bat_rbi)
           VALUES (%s, %s, %s, 30, 120, 60, 25, 30, 50)""",
        (p, s.id, a.id),
    )
    play.update_league(db, league.id)

    hr = _feats(db, league.id, "game", "HR")
    assert hr and all(f["source"] == "backstory" for f in hr)
    assert hr[0]["player_id"] == p and hr[0]["on_date"].startswith("2029-05")
    assert _feats(db, league.id, "streak", "twin")[0]["value"] == 30
    assert db.execute(
        "SELECT records_seeded FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()["records_seeded"]
    # No marks in a league with a backstory.
    ctx = records.book(db, league.id, "game", None, None)
    card = next(
        c for _, cs in ctx["rec_sections"] for c in cs if c.label == "Home runs"
    )
    assert card.mark is None and card.holders[0]["player_id"] == p


# ── Postseason, GMs, watch, badge ────────────────────────────────────────────


def test_series_records_add_up_a_playoff_series(db_conn, lg):
    db = db_conn
    lid = lg["league"].id
    series = _id()
    db.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
        (series, lg["s"].id),
    )
    p = _player(db, lg["league"], "October")
    for day in range(1, 5):
        g = _game(db, lg["s"], lg["a"], lg["b"], f"2030-10-{day:02d}", series_id=series)
        _box(db, g, p, lg["a"], lg["b"], bat_ab=4, bat_hits=2, bat_home_runs=2)
    ctx = records.book(db, lid, "postseason", None, None)
    sections = dict(ctx["rec_sections"])
    hr = next(c for c in sections["Series"] if c.label == "Home runs")
    assert hr.holders[0]["player_id"] == p and hr.holders[0]["shown"] == "8"
    assert "Finals" in hr.holders[0]["detail"]
    avg = next(
        c for c in sections["Series rates: top ten"] if c.label == "Batting average"
    )
    assert avg.listing and avg.rows[0]["shown"] == ".500"
    titles = next(c for c in sections["Titles"] if c.label == "Most titles")
    assert titles.holders[0]["name"] == "Tokyo Samurai"


def test_gm_records(db_conn, lg):
    db = db_conn
    uid = _id()
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'Josh', 'josh')",
        (uid, _id()),
    )
    db.execute(
        """INSERT INTO gm_career_seasons (user_id, league_id, season_id, league_name,
               season_year, team_city, team_mascot, wins, losses, playoff_result, final)
           VALUES (%s, %s, %s, 'L', 2030, 'Tokyo', 'Samurai', 100, 62, 'Champion', TRUE)""",
        (uid, lg["league"].id, lg["s"].id),
    )
    ctx = records.book(db, lg["league"].id, "gms", None, None, uid)
    cards = {c.label: c for c in ctx["rec_sections"][0][1]}
    assert cards["Most titles"].holders[0]["name"] == "josh"
    assert cards["Most titles"].holders[0]["is_mine"]
    assert cards["Best season"].holders[0]["shown"] == "100-62"
    # One row per season, not one per team in the league (Josh: the season
    # was listed once per club, "Done 30 times").
    assert cards["Most titles"].holders[0]["shown"] == "1"
    assert cards["Most wins"].holders[0]["shown"] == "100"
    assert len(cards["Best season"].holders) == 1


def test_record_watch_and_the_badge(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    # Three earlier seasons: the record is 40 HR.
    old = _player(db, lg["league"], "Old")
    for year in (2027, 2028, 2029):
        s = factory.season(year=year)
        factory.league_season(lg["league"], s)
        _game(db, s, lg["a"], lg["b"], f"{year}-05-01")
        db.execute(
            """INSERT INTO player_season_stats (player_id, season_id, team_id,
                   bat_games_played, bat_home_runs) VALUES (%s, %s, %s, 1, %s)""",
            (old, s.id, lg["a"].id, 40 if year == 2028 else 10),
        )
    hot = _player(db, lg["league"], "Hot")
    for day in range(40):
        _game(
            db,
            lg["s"],
            lg["a"],
            lg["b"],
            f"2030-{4 + day // 28:02d}-{day % 28 + 1:02d}",
        )
    # The rest of a 162-game schedule, unplayed.
    for _ in range(121):
        db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
                   completed) VALUES (%s, '2030-09-01', %s, %s, %s, 0)""",
            (_id(), lg["s"].id, lg["a"].id, lg["b"].id),
        )
    # 15 in 40 games is on pace for 60.
    db.execute(
        """INSERT INTO player_season_stats (player_id, season_id, team_id,
               bat_games_played, bat_home_runs) VALUES (%s, %s, %s, 40, 15)""",
        (hot, lg["s"].id, lg["b"].id),
    )
    rows = watch.watch(db, lid, lg["s"].id, lg["b"].id)
    pace = [r for r in rows if r["kind"] == "pace" and r["player_id"] == hot]
    assert pace and pace[0]["record"] == "40" and pace[0]["is_mine"]

    held._CACHE.clear()
    assert held.held(db, lid, old) == [
        "Home runs in a season (40)",
        "Home runs in a career (60)",
    ]
    assert held.held(db, lid, _id()) == []


@pytest.mark.parametrize("view", ["game", "streaks", "postseason", "gms"])
def test_every_new_view_renders(db_conn, lg, view):
    from src.web.utils import templates

    ctx = records.book(db_conn, lg["league"].id, view, lg["a"].id, None)
    ctx["league_id"] = lg["league"].id
    html = templates.env.get_template("dashboard/partials/records.html").render(**ctx)
    assert "Records" in html


def test_replay_is_steady_for_a_seed():
    ln = {"pitch_games_played": 30, "pitch_games_started": 30, "pitch_outs": 600,
          "pitch_strike_outs": 200, "pitch_wins": 15, "pitch_losses": 8}  # fmt: skip
    a = replay._pitcher_games(
        ln, 162, np.random.default_rng(random.Random(3).randrange(9))
    )
    assert a["PK"].sum() == 200
    assert (a["dec"] == 1).sum() == 15 and (a["dec"] == -1).sum() == 8
