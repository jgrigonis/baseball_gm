"""Attendance and stadium capacity (Josh, 2026-11-11; src/league/finances.py
crowd)."""

import datetime
import uuid

from src.league import finances as fn
from src.league import owner_scoring as sc
from tests.api.test_budgets import _owned, client_for, lg  # noqa: F401 (fixtures)


def test_crowds_follow_fans_market_and_seats():
    mid = fn.expected_crowd(50, 3)
    assert 29_000 < mid < 32_000
    assert fn.expected_crowd(95, 3) > fn.CROWD_CAPACITY > fn.expected_crowd(70, 3)
    assert fn.expected_crowd(50, 5) > mid > fn.expected_crowd(50, 1)
    # Cheap tickets fill seats.
    assert fn.expected_crowd(50, 3, 1) > mid > fn.expected_crowd(50, 3, 10)
    # Weekends draw more, and a week evens out.
    sat, tue = datetime.date(2026, 5, 2), datetime.date(2026, 5, 5)
    assert (
        fn.expected_crowd(50, 3, None, sat) > mid > fn.expected_crowd(50, 3, None, tue)
    )
    assert abs((3 * fn.CROWD_WEEKEND + 4 * fn.CROWD_WEEKDAY) / 7 - 1) < 0.01
    # The seats cap the crowd; the opener sells out.
    assert fn.crowd(60_000, 42_000) == 42_000
    assert fn.crowd(20_000, 42_000, opener=True) == 42_000
    assert fn.crowd(30_000, 42_000) == 30_000
    assert fn.crowd(30_000, 42_000, opponent=1.1, form=1.05) > 30_000
    # Every park holds the same until a new stadium opens.
    assert fn.capacity([]) == fn.capacity(["club_seats", "suites"]) == 42_000
    assert fn.capacity(["stadium_basic"]) == 45_000
    assert fn.capacity(["stadium_showpiece#2", "suites"]) == 52_000


def test_visitors_and_form_move_the_crowd_a_little():
    assert fn.opponent_mult(80, 50) == 1 + fn.CROWD_OPPONENT
    assert fn.opponent_mult(50, 50) == 1
    assert fn.opponent_mult(35, 50) < 1
    assert fn.form_mult(0, 0) == 1
    # A hot start counts for less than a hot season.
    assert 1 < fn.form_mult(4, 1) < fn.form_mult(40, 10) <= 1 + fn.CROWD_FORM_MAX
    assert fn.form_mult(10, 40) == 1 - fn.CROWD_FORM_MAX


def test_the_gate_follows_crowds_against_what_was_expected():
    tickets = 300_000_000
    assert fn.crowd_money(tickets, 81_000, 81_000, 81, 81) == 0
    more = fn.crowd_money(tickets, 89_100, 81_000, 81, 81)
    assert more == round(tickets * fn.GATE_SHARE * 0.10 / 100_000) * 100_000
    assert fn.crowd_money(tickets, 72_900, 81_000, 81, 81) == -more
    # Games without a crowd (played before crowds were counted) count as
    # drawing what was expected.
    assert fn.crowd_money(tickets, 44_550, 40_500, 40, 81) < more
    assert fn.crowd_money(tickets, 0, 0, 0, 81) == 0


def test_the_attendance_score_reads_crowds_and_a_full_park():
    assert fn.attendance_score(29_400, 29_400, 42_000) == 0
    assert fn.attendance_score(42_000, 38_000, 42_000) > 0.8
    assert fn.attendance_score(20_000, 25_000, 42_000) == -1
    season = sc.TeamSeason(
        wins=81, losses=81, payroll=1, budget=1, fans_before=50, fans_after=90,
        crowd_score=-0.5,
    )  # fmt: skip
    assert sc.score_dimensions(season, {}, True)["attendance"] == -0.5
    old = sc.TeamSeason(wins=81, losses=81, payroll=1, budget=1, fans_after=80)
    assert sc.score_dimensions(old, {}, True)["attendance"] == 1.0


def _home_games(x, n, start=datetime.date(2026, 4, 1)):
    ids = []
    for i in range(n):
        g = uuid.uuid4().hex
        x.db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                   away_team_id, winner_id, completed)
               VALUES (%s, %s, %s, %s, %s, %s, 1)""",
            (
                g,
                (start + datetime.timedelta(days=i)).isoformat(),
                x.season.id,
                x.mine.id,
                x.theirs.id,
                x.mine.id,
            ),
        )
        ids.append(g)
    return ids


def _crowds(x, ids, start=datetime.date(2026, 4, 1)):
    for i, g in enumerate(ids):
        x.budgets.game_crowd(
            x.league.id,
            x.season.id,
            g,
            x.mine.id,
            x.theirs.id,
            start + datetime.timedelta(days=i),
        )


def test_every_home_game_gets_a_crowd_and_the_season_counts_them(lg):  # noqa: F811
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    ids = _home_games(x, 25)
    _crowds(x, ids)
    rows = x.db.execute(
        "SELECT id, attendance, crowd_expected FROM games WHERE season_id = %s",
        (x.season.id,),
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    assert by_id[ids[0]]["attendance"] == fn.CROWD_CAPACITY  # the opener
    assert all(0 < r["attendance"] <= fn.CROWD_CAPACITY for r in rows)
    assert all(r["crowd_expected"] > 0 for r in rows)
    seen = x.budgets.crowds(x.league.id, 2026)[x.mine.id]
    assert seen["counted"] == seen["games"] == 25
    assert seen["capacity"] == fn.CROWD_CAPACITY and seen["sellouts"] >= 1
    assert seen["attendance"] == sum(r["attendance"] for r in rows)
    # The season's end records them, and the gate counts in the profit.
    x.budgets.assess(x.league.id, 2026)
    stored = x.db.execute(
        """SELECT attendance, crowd_games, capacity, sellouts, crowd_revenue
           FROM team_budgets WHERE league_id = %s AND team_id = %s AND year = 2026""",
        (x.league.id, x.mine.id),
    ).fetchone()
    assert stored["attendance"] == seen["attendance"]
    assert stored["crowd_games"] == 25 and stored["capacity"] == fn.CROWD_CAPACITY
    assert stored["crowd_revenue"] is not None
    books = x.budgets.books(x.league.id, x.mine.id, 2026)[0]
    assert books["crowds"] == stored["crowd_revenue"] and books["other"] == 0


def test_speed_blitz_has_no_crowds(lg):  # noqa: F811
    x = lg(mode="speed_blitz")
    (g,) = _home_games(x, 1)
    assert (
        x.budgets.game_crowd(
            x.league.id, x.season.id, g, x.mine.id, x.theirs.id, datetime.date.today()
        )
        is None
    )


def test_the_budget_tab_and_box_score_show_crowds(lg, client_for):  # noqa: F811
    x = lg()
    _owned(x, spending=95)
    x.budgets.for_league(x.league.id, 2026)
    ids = _home_games(x, 3)
    _crowds(x, ids)
    client = client_for(x)
    page = client.get(f"/leagues/{x.league.id}/budget").text
    assert 'id="crowds"' in page and "42,000" in page and "Average crowd" in page
    assert "Sellouts" in page
    assert "45,000 seats (+3,000)" in page  # the Basic stadium's offer
    panel = client.get(f"/leagues/{x.league.id}/games/{ids[0]}/panel").text
    assert "Attendance 42,000, sellout" in panel
