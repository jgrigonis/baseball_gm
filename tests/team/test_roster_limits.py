# tests/team/test_roster_limits.py
"""A Blitz team's 40-man is kept between 25 and 40 before it plays (Long
Form's 26-man: tests/team/test_active_roster.py)."""

from src.api.services.injury_news import take_injury_news
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.team.roster_limits import enforce_roster_limits, playing_count


def _team(factory, on_forty, in_org, human=True, mode="blitz"):
    league = factory.league(state="season", mode=mode)
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=not human)
    forty = [factory.rated_player(team, league, 55) for _ in range(on_forty)]
    org = [
        factory.rated_player(team, league, 40 + i, status="minors")
        for i in range(in_org)
    ]
    return league, team, gm, forty, org


def test_a_short_roster_calls_up_the_best_of_the_organization(db_conn, factory):
    league, team, gm, _, org = _team(factory, on_forty=23, in_org=4)
    moves = enforce_roster_limits(db_conn, league.id, team.id, "blitz")
    assert playing_count(db_conn, team.id) == 25
    # The two best: 43 and 42.
    assert {m["player_id"] for m in moves} == {org[3].id, org[2].id}
    assert all(m["to"] == "40man" for m in moves)


def test_healthy_players_are_called_up_before_injured_ones(db_conn, factory):
    league, team, _, _, org = _team(factory, on_forty=24, in_org=2)
    db_conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, return_date)
           VALUES (%s, %s, '2099-01-01')""",
        (org[1].id, league.id),
    )
    moves = enforce_roster_limits(db_conn, league.id, team.id, "blitz")
    assert [m["player_id"] for m in moves] == [org[0].id]


def test_an_overfull_roster_sends_the_lowest_rated_down(db_conn, factory):
    league, team, _, _, _ = _team(factory, on_forty=40, in_org=0)
    worst = factory.rated_player(team, league, 41)
    moves = enforce_roster_limits(db_conn, league.id, team.id, "blitz")
    assert moves == [{"player_id": worst.id, "name": "Test Player", "to": "minors"}]
    assert PlayerStatusRepository(db_conn).get_status(worst.id) == "minors"


def test_a_legal_roster_is_left_alone(db_conn, factory):
    league, team, _, _, _ = _team(factory, on_forty=30, in_org=3)
    assert enforce_roster_limits(db_conn, league.id, team.id, "blitz") == []


def test_the_gm_hears_about_each_move(db_conn, factory):
    league, team, gm, _, _ = _team(factory, on_forty=24, in_org=1)
    enforce_roster_limits(db_conn, league.id, team.id, "blitz")
    news = take_injury_news(db_conn, gm.id)
    assert news["roster_moves"] == [{"name": "Test Player", "to": "40man"}]
