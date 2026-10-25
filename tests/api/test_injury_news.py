# tests/api/test_injury_news.py
"""Each human GM hears about injuries on their own team, whoever ran the sim."""

from datetime import date, timedelta

from src.api.services.injury_news import InjuryNews, take_injury_news


def _player_on(db, factory, team, name):
    p = factory.player_row()
    db.execute(
        "UPDATE players SET first_name = %s, last_name = '' WHERE id = %s",
        (name, p.id),
    )
    db.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (team.id, p.id)
    )
    return p


def _injure(db, league, player, days):
    return_date = (date.today() + timedelta(days=days)).isoformat()
    db.execute(
        "INSERT INTO player_injuries (player_id, league_id, games_remaining, return_date)"
        " VALUES (%s, %s, %s, %s)",
        (player.id, league.id, days, return_date),
    )


def test_every_human_gm_gets_their_own_news(db_conn, factory):
    league = factory.league(state="season")
    team_a, team_b, team_ai = factory.team(), factory.team(), factory.team()
    gm_a = factory.gm(team=team_a, league=league, is_ai=False)
    gm_b = factory.gm(team=team_b, league=league, is_ai=False)
    factory.gm(team=team_ai, league=league, is_ai=True)
    hurt_a = _player_on(db_conn, factory, team_a, "Alice")
    back_b = _player_on(db_conn, factory, team_b, "Bob")
    hurt_ai = _player_on(db_conn, factory, team_ai, "Robot")
    _injure(db_conn, league, back_b, 3)

    news = InjuryNews(db_conn, league.id)
    # The "sim": Alice and Robot get hurt, Bob comes back.
    _injure(db_conn, league, hurt_a, 10)
    _injure(db_conn, league, hurt_ai, 5)
    db_conn.execute("DELETE FROM player_injuries WHERE player_id = %s", (back_b.id,))
    news.record()

    a = take_injury_news(db_conn, gm_a.id)
    b = take_injury_news(db_conn, gm_b.id)
    assert a == {
        "new_injuries": [{"name": "Alice ", "days": 10, "is_pitcher": False}],
        "returned": [],
    }
    assert b == {
        "new_injuries": [],
        "returned": [{"name": "Bob ", "is_pitcher": False, "on_40man": False}],
    }


def test_news_is_shown_once(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    player = _player_on(db_conn, factory, team, "Alice")

    news = InjuryNews(db_conn, league.id)
    _injure(db_conn, league, player, 10)
    news.record()

    assert len(take_injury_news(db_conn, gm.id)["new_injuries"]) == 1
    assert take_injury_news(db_conn, gm.id) == {"new_injuries": [], "returned": []}
