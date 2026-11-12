# tests/api/test_records.py
"""The record book (src/api/services/records): season, career and team
records, ties, qualifiers, franchise records and the page."""

import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import records
from src.api.services.records import core


def _id():
    return str(uuid.uuid4())


def _player(db, league, last, first="Test"):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, %s, %s, 'R', 'R', 'of', %s)",
        (pid, first, last, league.id),
    )
    return pid


def _line(db, pid, season, team, **cols):
    cols = {"bat_games_played": 100, **cols}
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    db.execute(
        f"INSERT INTO player_season_stats (player_id, season_id, team_id, {names})"
        f" VALUES (%s, %s, %s, {marks})",
        (pid, season.id, team.id, *cols.values()),
    )


def _game(db, season, home, away, hs=5, as_=3, date="2025-06-01", line=None,
          innings=9, series_id=None, completed=1):  # fmt: skip
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed,
               innings_played, line_score)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (gid, date, season.id, series_id, home.id, away.id, hs, as_,
         home.id if hs > as_ else away.id, completed, innings,
         Jsonb(line) if line else None),
    )  # fmt: skip
    if completed:
        for team, runs, won in ((home, hs, hs > as_), (away, as_, as_ > hs)):
            db.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
                " VALUES (%s, %s, %s, %s, %s)",
                (gid, team.id, runs, int(won), int(not won)),
            )
    return gid


@pytest.fixture
def lg(db_conn, factory):
    """2000 is a backstory season, 2001 finished, 2002 under way. Two clubs."""
    db = db_conn
    league = factory.league(state="season")
    tokyo = factory.team(city="Tokyo", mascot="Samurai")
    lagos = factory.team(city="Lagos", mascot="Leopards")
    seasons = {}
    for year in (2000, 2001, 2002):
        s = factory.season(year=year)
        db.execute(
            "UPDATE seasons SET is_backstory = %s WHERE id = %s", (year == 2000, s.id)
        )
        factory.league_season(league, s)
        for t in (tokyo, lagos):
            factory.league_season_team(league, s, t)
        seasons[year] = s
        # Two games each season: 2000 and 2001 are over, 2002 has one to play.
        _game(db, s, tokyo, lagos, date=f"{year}-05-01")
        _game(db, s, tokyo, lagos, date=f"{year}-05-02", completed=int(year != 2002))
    return {"league": league, "tokyo": tokyo, "lagos": lagos, "s": seasons}


def _book(db, lg, view="season", team=None, mine=None):
    return records.book(db, lg["league"].id, view, team, mine)


def _card(ctx, label, section=None):
    for title, cards in ctx["rec_sections"]:
        if section and title != section:
            continue
        for c in cards:
            if c.label == label:
                return c
    raise KeyError(label)


# ── Ranking ───────────────────────────────────────────────────────────────────


def test_ties_share_a_rank_and_the_first_there_leads():
    perfs = [
        {"value": 50, "shown": "50", "order": "02001", "name": "B"},
        {"value": 50, "shown": "50", "order": "02000", "name": "A"},
        {"value": 48, "shown": "48", "order": "01999", "name": "C"},
        {"value": 40, "shown": "40", "order": "01999", "name": "D"},
    ]
    c = core.card("hr", "Home runs", perfs)
    assert [h["name"] for h in c.holders] == ["A", "B"]
    assert [(r["name"], r["rank"]) for r in c.others] == [("C", 3), ("D", 4)]
    assert c.times == 2


def test_everyone_tied_for_first_stays_past_the_list_size():
    perfs = [
        {"value": 3, "shown": "3", "order": f"{i:05d}", "name": str(i)}
        for i in range(8)
    ]
    c = core.card("hr", "HR", perfs)
    assert len(c.holders) == 8
    assert c.more_holders == 5


def test_a_floor_holds_until_beaten_not_tied():
    tied = [{"value": 5, "shown": "5", "order": "1", "name": "A"}]
    c = core.card("h", "Hits", tied, floor=5)
    assert c.mark["shown"] == "5" and not c.holders
    assert [r["name"] for r in c.rows] == ["A"]
    beat = tied + [{"value": 6, "shown": "6", "order": "2", "name": "B"}]
    c = core.card("h", "Hits", beat, floor=5)
    assert c.mark is None and [h["name"] for h in c.holders] == ["B"]


# ── Season ────────────────────────────────────────────────────────────────────


def test_backstory_seasons_count_and_ties_go_to_the_earlier_year(db_conn, lg):
    db = db_conn
    old = _player(db, lg["league"], "Old")
    new = _player(db, lg["league"], "New")
    _line(db, old, lg["s"][2000], lg["tokyo"], bat_home_runs=50)
    _line(db, new, lg["s"][2001], lg["lagos"], bat_home_runs=50)

    c = _card(_book(db, lg), "Home runs")

    assert [h["player_id"] for h in c.holders] == [old, new]
    assert c.holders[0]["detail"] == "2000"


def test_a_split_season_adds_up_for_the_league_but_not_the_club(db_conn, lg):
    db = db_conn
    p = _player(db, lg["league"], "Mover")
    other = _player(db, lg["league"], "Stayer")
    _line(db, p, lg["s"][2001], lg["tokyo"], bat_home_runs=20)
    _line(db, p, lg["s"][2001], lg["lagos"], bat_home_runs=25)
    _line(db, other, lg["s"][2001], lg["tokyo"], bat_home_runs=30)

    league = _card(_book(db, lg), "Home runs")
    assert league.holders[0]["player_id"] == p
    assert league.holders[0]["shown"] == "45"
    assert league.holders[0]["team"] == "2 teams"

    club = _card(_book(db, lg, team=lg["tokyo"].id), "Home runs")
    assert club.holders[0]["player_id"] == other
    assert [r["shown"] for r in club.rows] == ["30", "20"]


def test_the_season_under_way_counts_but_is_marked_live(db_conn, lg):
    db = db_conn
    p = _player(db, lg["league"], "Hot")
    _line(db, p, lg["s"][2002], lg["tokyo"], bat_hits=200)
    c = _card(_book(db, lg), "Hits")
    assert c.holders[0]["player_id"] == p and c.holders[0]["active"]


def test_rate_records_need_a_finished_season_and_enough_plate_appearances(db_conn, lg):
    db = db_conn
    # 2 team games a season, so 3.1 PA a game is 6 PA.
    ok = _player(db, lg["league"], "Qualified")
    short = _player(db, lg["league"], "Short")
    now = _player(db, lg["league"], "Now")
    _line(db, ok, lg["s"][2001], lg["tokyo"], bat_ab=8, bat_hits=4)
    _line(db, short, lg["s"][2001], lg["tokyo"], bat_ab=5, bat_hits=5)
    _line(db, now, lg["s"][2002], lg["tokyo"], bat_ab=8, bat_hits=8)

    c = _card(_book(db, lg), "Batting average")

    assert [r["player_id"] for r in c.rows] == [ok]
    assert c.holders[0]["shown"] == ".500"


def test_era_is_lower_is_better(db_conn, lg):
    db = db_conn
    ace = _player(db, lg["league"], "Ace")
    meh = _player(db, lg["league"], "Meh")
    for pid, er in ((ace, 1), (meh, 4)):
        _line(db, pid, lg["s"][2001], lg["tokyo"], bat_games_played=0,
              pitch_games_played=2, pitch_outs=27, pitch_earned_runs=er)  # fmt: skip
    c = _card(_book(db, lg), "ERA")
    assert [r["player_id"] for r in c.rows] == [ace, meh]
    assert c.holders[0]["shown"] == "1.00"


# ── Career ────────────────────────────────────────────────────────────────────


def test_career_adds_every_season_and_rate_stats_need_3000_pa(db_conn, lg):
    db = db_conn
    vet = _player(db, lg["league"], "Vet")
    kid = _player(db, lg["league"], "Kid")
    for y in (2000, 2001, 2002):
        _line(
            db,
            vet,
            lg["s"][y],
            lg["tokyo"],
            bat_ab=1100,
            bat_hits=330,
            bat_home_runs=40,
        )
    _line(
        db, kid, lg["s"][2002], lg["lagos"], bat_ab=500, bat_hits=250, bat_home_runs=60
    )

    ctx = _book(db, lg, "career")
    hr = _card(ctx, "Home runs")
    assert hr.holders[0]["player_id"] == vet and hr.holders[0]["shown"] == "120"
    assert hr.holders[0]["detail"] == "2000–2002"
    assert hr.holders[0]["active"]
    avg = _card(ctx, "Batting average")
    assert [r["player_id"] for r in avg.rows] == [vet]


# ── Team ──────────────────────────────────────────────────────────────────────


def test_team_records_from_games(db_conn, lg):
    db = db_conn
    s = lg["s"][2001]
    _game(db, s, lg["lagos"], lg["tokyo"], hs=19, as_=2, date="2001-06-01",
          line={"away": [0, 2, 0, 0, 0, 0, 0, 0, 0], "home": [0, 11, 0, 3, 0, 5, 0, 0, 0]})  # fmt: skip
    _game(db, s, lg["tokyo"], lg["lagos"], hs=3, as_=2, date="2001-06-02", innings=16)

    ctx = _book(db, lg, "team", mine=lg["lagos"].id)
    runs = _card(ctx, "Most runs in a game")
    assert (
        runs.holders[0]["name"] == "Lagos Leopards" and runs.holders[0]["shown"] == "19"
    )
    assert runs.holders[0]["is_mine"]
    assert _card(ctx, "Biggest win").holders[0]["shown"] == "+17"
    inning = _card(ctx, "Most runs in an inning").holders[0]
    assert inning["shown"] == "11" and inning["team"].startswith("2nd inning")
    assert _card(ctx, "Longest game").holders[0]["shown"] == "16 inn"
    # A backstory game's innings never count: its long game and big inning
    # are left out.
    _game(db, lg["s"][2000], lg["lagos"], lg["tokyo"], hs=30, as_=29, innings=19,
          date="2000-06-03", line={"away": [29], "home": [30]})  # fmt: skip
    ctx = _book(db, lg, "team", mine=lg["lagos"].id)
    assert _card(ctx, "Longest game").holders[0]["shown"] == "16 inn"
    assert _card(ctx, "Most runs in an inning").holders[0]["shown"] == "11"
    # Tokyo won both games in 2000; 2002 is still going, so it's not "fewest".
    wins = _card(ctx, "Most wins")
    assert wins.holders[0]["name"] == "Tokyo Samurai"
    fewest = _card(ctx, "Fewest wins")
    assert all(r["detail"] != "2002" for r in fewest.rows)


# ── Page ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(db_conn, lg):
    app.dependency_overrides[get_db] = lambda: db_conn
    gm = {"id": None, "team_id": lg["tokyo"].id}
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: gm
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("view", ["season", "career", "team", "nonsense"])
def test_the_page_renders_every_view(db_conn, lg, client, view):
    p = _player(db_conn, lg["league"], "Slugger")
    _line(
        db_conn, p, lg["s"][2001], lg["tokyo"], bat_home_runs=44, bat_ab=10, bat_hits=5
    )
    r = client.get(
        f"/leagues/{lg['league'].id}/records?view={view}&team={lg['tokyo'].id}",
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Records" in r.text
    assert "Tokyo Samurai" in r.text
