# tests/api/test_hall_of_fame.py
"""Hall of Fame elections against the database (src/api/services/
hall_of_fame.py): who makes the ballot, when the votes are held, what's
kept, and the page, panel badge and news that show it."""

import pytest

from src.api.services import hall_of_fame, season_value
from src.api.services.news import Names, events
from src.web.utils import templates

FIRST = 2000  # the league's first played season; backstory before it


@pytest.fixture
def lg(db_conn, factory, monkeypatch):
    """Twelve backstory seasons (1988-1999), then seven played ones (2000-2006),
    every one's awards done, and two teams."""
    db = db_conn
    league = factory.league(state="offseason")
    teams = [factory.team(city="Tokyo", mascot="Samurai"), factory.team()]
    seasons = {}
    for year in range(1988, 2007):
        s = factory.season(year=year)
        db.execute(
            "UPDATE seasons SET is_backstory = %s WHERE id = %s", (year < FIRST, s.id)
        )
        factory.league_season(league, s)
        db.execute(
            "UPDATE league_seasons SET awards_done = TRUE WHERE season_id = %s",
            (s.id,),
        )
        for t in teams:
            factory.league_season_team(league, s, t)
        seasons[year] = s
    war = {}
    # Every season's WAR comes from here instead of a whole league's stats.
    monkeypatch.setattr(
        season_value,
        "season_values",
        lambda conn, sid: {
            pid: {"WAR": w, "hitter": True, "Def": None} for pid, w in war.items()
        },
    )
    return {"league": league, "teams": teams, "seasons": seasons, "war": war}


def _career(db, factory, lg, years, retired, war=8.0):
    """A hitter who played `years` and retired after `retired`."""
    p = factory.prospect(lg["league"].id)
    lg["war"][p.id] = war
    for y in years:
        db.execute(
            """INSERT INTO player_season_stats (player_id, season_id, team_id,
                   bat_games_played, bat_ab, bat_hits, bat_home_runs)
               VALUES (%s, %s, %s, 150, 550, 170, 30)""",
            (p.id, lg["seasons"][y].id, lg["teams"][0].id),
        )
    db.execute(
        "INSERT INTO player_retirements (player_id, league_id, season_id, former_team_id)"
        " VALUES (%s, %s, %s, %s)",
        (p.id, lg["league"].id, lg["seasons"][retired].id, lg["teams"][0].id),
    )
    return p


def _ballot(db, league_id, year):
    rows = db.execute(
        """SELECT hb.* FROM hall_ballot hb
           JOIN hall_elections he ON he.season_id = hb.season_id
           WHERE hb.league_id = %s AND he.year = %s""",
        (league_id, year),
    ).fetchall()
    return {r["player_id"]: r for r in rows}


def test_first_vote_comes_five_seasons_after_the_league_starts(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    star = _career(db, factory, lg, range(1990, 2001), retired=2000)

    hall_of_fame.decide_league(db, lid)

    years = hall_of_fame.election_years(db, lid)
    assert years == [2006, 2005]  # 2000 + 5 is the first
    assert set(_ballot(db, lid, 2005)) == {star.id}
    assert hall_of_fame.has_hall(db, lid)


def test_backstory_retirees_and_short_careers_stay_off(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    _career(db, factory, lg, range(1988, 1999), retired=1998)  # retired pre-league
    _career(db, factory, lg, range(1992, 2001), retired=2000)  # 9 seasons
    ok = _career(db, factory, lg, range(1991, 2001), retired=2000)  # 10

    hall_of_fame.decide_league(db, lid)

    assert set(_ballot(db, lid, 2005)) == {ok.id}


def test_holdovers_come_back_a_year_older(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    p = _career(db, factory, lg, range(1990, 2001), retired=2000, war=0.0)
    # Last year's vote, already held: he got 40%.
    sid = lg["seasons"][2005].id
    db.execute(
        "INSERT INTO hall_elections (season_id, league_id, year, ballots)"
        " VALUES (%s, %s, 2005, 4)",
        (sid, lid),
    )
    db.execute(
        """INSERT INTO hall_ballot (season_id, player_id, league_id, votes, share,
               year_on_ballot, outcome) VALUES (%s, %s, %s, 2, 0.4, 3, 'returning')""",
        (sid, p.id, lid),
    )

    hall_of_fame.decide_league(db, lid)

    row = _ballot(db, lid, 2006)[p.id]
    assert row["year_on_ballot"] == 4
    assert row["outcome"] in ("returning", "dropped")


def test_no_vote_until_the_finals_are_over(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    _career(db, factory, lg, range(1990, 2001), retired=2000)
    db.execute(
        "UPDATE league_seasons SET awards_done = FALSE WHERE season_id = %s",
        (lg["seasons"][2006].id,),
    )

    hall_of_fame.decide_league(db, lid)
    hall_of_fame.decide_league(db, lid)  # nothing held twice

    assert hall_of_fame.election_years(db, lid) == [2005]


def test_an_inductee_gets_a_plaque_a_badge_and_a_story(db_conn, factory, lg):
    db = db_conn
    lid = lg["league"].id
    # 30 WAR a season, even weighted down for the backstory: a sure thing.
    great = _career(db, factory, lg, range(1991, 2001), retired=2000, war=30.0)

    hall_of_fame.decide_league(db, lid)

    row = _ballot(db, lid, 2005)[great.id]
    assert row["outcome"] == "elected"
    plaques = hall_of_fame.inductees(db, lid)
    assert [p["player_id"] for p in plaques] == [great.id]
    assert plaques[0]["team"] == "Tokyo Samurai"
    assert "WAR" in plaques[0]["line"]
    # Nine of his ten seasons were before the league: they count three quarters.
    assert row["summary"]["backstory_seasons"] == 9
    assert row["summary"]["weighted_war"] == 232.5
    assert row["summary"]["war"] == 300.0

    badge = hall_of_fame.badge(db, great.id)
    assert badge["elected"] and badge["text"] == "Hall of Fame 2005"

    html = templates.get_template("dashboard/partials/hall_of_fame.html").render(
        league_id=lid,
        inductees=plaques,
        election_years=[2006, 2005],
        ballot_year=2005,
        ballot=hall_of_fame.ballot(db, lid, 2005),
        elect_pct=75,
        keep_pct=5,
        first_year=2005,
    )
    assert "Class of 2005" in html
    assert "Elected" in html

    events.hall_of_fame(db, Names(db, lid), lid, lg["seasons"][2005].id, 2005)
    story = db.execute(
        "SELECT headline FROM league_news WHERE league_id = %s AND kind = 'hall_of_fame'",
        (lid,),
    ).fetchone()
    assert "elected to the Hall of Fame" in story["headline"]


def test_the_page_before_any_vote(db_conn, factory, lg):
    html = templates.get_template("dashboard/partials/hall_of_fame.html").render(
        league_id=lg["league"].id,
        inductees=[],
        election_years=[],
        ballot_year=None,
        ballot=[],
        elect_pct=75,
        keep_pct=5,
        first_year=2005,
    )
    assert "The first one comes after the 2005 season" in html
