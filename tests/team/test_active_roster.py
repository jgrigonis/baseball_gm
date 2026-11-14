# tests/team/test_active_roster.py
"""
Long Form plays off the 26-man (Josh, 2026-11-14): 25 to 26 active players
with at most 13 pitchers, 28 and 14 from September 1 through the regular
season, and at most 40 on the 40-man. The game fixes a roster that's out of
line before the team plays; AI teams also bench players hurt for more than
a few days and fill every spot.
"""

from src.api.services.injury_news import take_injury_news
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.team.roster_limits import active_limits, enforce_roster_limits

APRIL = "2025-05-10"
SEPT = "2025-09-01"


def _count(db_conn, team_id, status, pitchers=None):
    q = """SELECT COUNT(*) AS n FROM team_players tp
           JOIN player_status ps ON ps.player_id = tp.player_id
           JOIN players p ON p.id = tp.player_id
           WHERE tp.team_id = %s AND ps.status = %s"""
    if pitchers is not None:
        q += " AND p.position " + ("=" if pitchers else "<>") + " 'sp'"
    return db_conn.execute(q, (team_id, status)).fetchone()["n"]


def _team(
    factory, hitters=13, pitchers=13, reserve_h=4, reserve_p=4, minors=4, human=True
):
    league = factory.league(state="season", mode="longform")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=not human)
    p = {"active_h": [], "active_p": [], "res_h": [], "res_p": [], "minors": []}
    for i in range(hitters):
        p["active_h"].append(
            factory.rated_player(team, league, 55 + i % 5, status="26man")
        )
    for i in range(pitchers):
        p["active_p"].append(
            factory.rated_player(team, league, 55 + i % 5, status="26man", pitcher=True)
        )
    for i in range(reserve_h):
        p["res_h"].append(factory.rated_player(team, league, 45 + i, status="40man"))
    for i in range(reserve_p):
        p["res_p"].append(
            factory.rated_player(team, league, 45 + i, status="40man", pitcher=True)
        )
    for i in range(minors):
        p["minors"].append(factory.rated_player(team, league, 40 + i, status="minors"))
    return league, team, gm, p


def _hurt(db_conn, league, player, until="2099-01-01"):
    db_conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, return_date)
           VALUES (%s, %s, %s)""",
        (player.id, league.id, until),
    )


def test_limits_expand_on_september_1_but_not_in_the_playoffs():
    assert active_limits("2025-08-31").max_active == 26
    assert active_limits("2025-08-31").max_pitchers == 13
    sept = active_limits(SEPT)
    assert (sept.max_active, sept.max_pitchers, sept.expanded) == (28, 14, True)
    assert sept.min_active == 28  # a full 28
    assert active_limits("2025-09-30", playoffs=True).max_active == 26
    assert active_limits("2025-10-03", playoffs=True).max_pitchers == 13


def test_a_legal_roster_is_left_alone(db_conn, factory):
    league, team, _, _ = _team(factory)
    assert enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL) == []


def test_too_many_pitchers_sends_the_worst_to_the_reserve(db_conn, factory):
    league, team, gm, p = _team(factory, hitters=12, pitchers=14)
    worst = factory.rated_player(team, league, 30, status="26man", pitcher=True)
    db_conn.execute(  # 27 on, 15 pitchers: two have to sit
        "UPDATE player_status SET status = '26man' WHERE player_id = %s", (worst.id,)
    )
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    assert worst.id in {m["player_id"] for m in moves}
    assert PlayerStatusRepository(db_conn).get_status(worst.id) == "40man"
    assert _count(db_conn, team.id, "26man", pitchers=True) == 13
    assert _count(db_conn, team.id, "26man") <= 26
    news = take_injury_news(db_conn, gm.id)["roster_moves"]
    assert {"name": "Test Player", "to": "40man", "why": "pitchers"} in news


def test_an_overfull_active_roster_sits_the_lowest_rated(db_conn, factory):
    league, team, _, _ = _team(factory, hitters=13, pitchers=13)
    worst = factory.rated_player(team, league, 31, status="26man")
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    assert [(m["player_id"], m["to"]) for m in moves] == [(worst.id, "40man")]


def test_a_short_roster_calls_up_from_the_reserve_first(db_conn, factory):
    league, team, _, p = _team(factory, hitters=10, pitchers=13)
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    # People's teams go back to the minimum, 25: two of the reserve hitters.
    assert _count(db_conn, team.id, "26man") == 25
    assert all(m["to"] == "26man" for m in moves)
    assert {m["player_id"] for m in moves} <= {x.id for x in p["res_h"]}


def test_a_short_roster_with_no_reserve_calls_up_a_minor_leaguer(db_conn, factory):
    league, team, _, p = _team(
        factory, hitters=11, pitchers=13, reserve_h=0, reserve_p=0
    )
    enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    assert PlayerStatusRepository(db_conn).get_status(p["minors"][-1].id) == "26man"
    assert _count(db_conn, team.id, "26man") == 25


def test_september_makes_people_carry_a_full_28(db_conn, factory):
    league, team, _, _ = _team(factory)
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", SEPT)
    assert len(moves) == 2 and all(m["to"] == "26man" for m in moves)
    assert _count(db_conn, team.id, "26man") == 28


def test_september_lets_people_carry_28(db_conn, factory):
    league, team, _, _ = _team(factory, hitters=14, pitchers=14)
    assert enforce_roster_limits(db_conn, league.id, team.id, "longform", SEPT) == []
    # The playoffs go back to 26 and 13.
    enforce_roster_limits(
        db_conn, league.id, team.id, "longform", "2025-10-01", playoffs=True
    )
    assert _count(db_conn, team.id, "26man") == 26
    # At most 13: the second cut is the lowest rated of either kind, and
    # equal ratings leave it to whichever the database lists first.
    assert _count(db_conn, team.id, "26man", pitchers=True) <= 13


def test_an_overfull_40_man_sends_reserves_down(db_conn, factory):
    league, team, _, p = _team(factory, reserve_h=8, reserve_p=8)  # 26 + 16 = 42
    enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    status = PlayerStatusRepository(db_conn)
    assert _count(db_conn, team.id, "26man") + _count(db_conn, team.id, "40man") == 40
    assert status.get_status(p["res_h"][0].id) == "minors"  # the two lowest
    assert status.get_status(p["res_p"][0].id) == "minors"


def test_people_keep_their_injured_players_active(db_conn, factory):
    league, team, _, p = _team(factory)
    _hurt(db_conn, league, p["active_h"][0])
    assert enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL) == []


def test_ai_benches_a_long_injury_for_a_like_replacement(db_conn, factory):
    league, team, _, p = _team(factory, human=False)
    _hurt(db_conn, league, p["active_p"][0])
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    status = PlayerStatusRepository(db_conn)
    assert status.get_status(p["active_p"][0].id) == "40man"
    # The best reserve pitcher takes his place.
    assert status.get_status(p["res_p"][-1].id) == "26man"
    assert len(moves) == 2
    assert _count(db_conn, team.id, "26man") == 26


def test_ai_keeps_a_player_hurt_for_a_day_or_two(db_conn, factory):
    league, team, _, p = _team(factory, human=False)
    _hurt(db_conn, league, p["active_h"][0], until="2025-05-12")
    assert enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL) == []


def test_ai_fills_28_in_september(db_conn, factory):
    league, team, _, _ = _team(factory, human=False)
    enforce_roster_limits(db_conn, league.id, team.id, "longform", SEPT)
    assert _count(db_conn, team.id, "26man") == 28
    assert _count(db_conn, team.id, "26man", pitchers=True) <= 14


def test_ai_puts_a_healed_player_back(db_conn, factory):
    league, team, _, p = _team(factory, human=False)
    star = factory.rated_player(team, league, 70, status="40man")
    _hurt(db_conn, league, star, until="2025-05-05")  # back five days ago
    enforce_roster_limits(db_conn, league.id, team.id, "longform", APRIL)
    status = PlayerStatusRepository(db_conn)
    assert status.get_status(star.id) == "26man"
    assert _count(db_conn, team.id, "26man") == 26


def test_blitz_ignores_the_26_man(db_conn, factory):
    league, team, _, _ = _team(factory, hitters=14, pitchers=16)
    db_conn.execute("UPDATE leagues SET mode = 'blitz' WHERE id = %s", (league.id,))
    assert enforce_roster_limits(db_conn, league.id, team.id, "blitz", APRIL) == []
