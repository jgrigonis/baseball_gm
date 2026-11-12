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


def _injure(db, league, player, days, injury_type=None):
    return_date = (date.today() + timedelta(days=days)).isoformat()
    db.execute(
        "INSERT INTO player_injuries"
        " (player_id, league_id, games_remaining, return_date, injury_type)"
        " VALUES (%s, %s, %s, %s, %s)",
        (player.id, league.id, days, return_date, injury_type),
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
        "rust_cleared": [],
        "roster_moves": [],
        "trades": [],
        "settings": [],
        "waivers": [],
    }
    assert b == {
        "new_injuries": [],
        "returned": [
            {"name": "Bob ", "length": 3, "is_pitcher": False, "on_40man": False}
        ],
        "rust_cleared": [],
        "roster_moves": [],
        "trades": [],
        "settings": [],
        "waivers": [],
    }


def test_news_names_the_injury(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    hurt = _player_on(db_conn, factory, team, "Alice")

    news = InjuryNews(db_conn, league.id)
    _injure(db_conn, league, hurt, 300, injury_type="torn_acl")
    news.record()

    (note,) = take_injury_news(db_conn, gm.id)["new_injuries"]
    assert note["injury"] == "Torn ACL"


def test_news_is_shown_once(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    player = _player_on(db_conn, factory, team, "Alice")

    news = InjuryNews(db_conn, league.id)
    _injure(db_conn, league, player, 10)
    news.record()

    assert len(take_injury_news(db_conn, gm.id)["new_injuries"]) == 1
    assert take_injury_news(db_conn, gm.id) == {
        "new_injuries": [],
        "returned": [],
        "rust_cleared": [],
        "roster_moves": [],
        "trades": [],
        "settings": [],
        "waivers": [],
    }


def _returned_is_pitcher(db, factory, position, outs=0, ab=0, skills=False):
    """Bring a player back from injury and return the news's is_pitcher."""
    league = factory.league(state="season")
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    if skills:
        player = factory.prospect(league.id)
        db.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
            (team.id, player.id),
        )
    else:
        player = _player_on(db, factory, team, "Pat")
    db.execute("UPDATE players SET position = %s WHERE id = %s", (position, player.id))
    if outs or ab:
        db.execute(
            "INSERT INTO player_season_stats"
            " (player_id, season_id, team_id, pitch_outs, bat_ab)"
            " VALUES (%s, %s, %s, %s, %s)",
            (player.id, season.id, team.id, outs, ab),
        )
    _injure(db, league, player, 3)

    news = InjuryNews(db, league.id)
    db.execute("DELETE FROM player_injuries WHERE player_id = %s", (player.id,))
    news.record()
    return take_injury_news(db, gm.id)["returned"][0]["is_pitcher"]


def test_returning_pitcher_with_no_stats_goes_by_position(db_conn, factory):
    assert _returned_is_pitcher(db_conn, factory, "sp") is True
    assert _returned_is_pitcher(db_conn, factory, "ss") is False


def test_returning_player_with_no_stats_goes_by_position_over_ratings(db_conn, factory):
    # The prospect's skills rate as a hitter, but he is listed as a pitcher
    assert _returned_is_pitcher(db_conn, factory, "sp", skills=True) is True


def test_returning_player_with_stats_goes_by_usage(db_conn, factory):
    assert _returned_is_pitcher(db_conn, factory, "ss", outs=30) is True
    assert _returned_is_pitcher(db_conn, factory, "sp", ab=40) is False
    # A pitcher who also bats a little is still a pitcher
    assert _returned_is_pitcher(db_conn, factory, "ss", outs=150, ab=20) is True


def test_a_return_says_what_the_injury_left(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    back = _player_on(db_conn, factory, team, "Tommy")
    _injure(db_conn, league, back, 3, "tommy_john")
    db_conn.execute(
        """INSERT INTO player_injury_log (player_id, injury_date, severity,
               games_missed, injury_type, outcome, effects)
           VALUES (%s, '2025-04-01', 'surgery', 400, 'tommy_john', 'stronger',
                   '{"strikes": 3}')""",
        (back.id,),
    )
    news = InjuryNews(db_conn, league.id)
    db_conn.execute("DELETE FROM player_injuries WHERE player_id = %s", (back.id,))
    news.record()
    (note,) = take_injury_news(db_conn, gm.id)["returned"]
    assert note["effect"] == "came back stronger (KK +3)"


# ── Rust wearing off ──────────────────────────────────────────────────────────


def _back_rusty(db, league, player, rust_days=20):
    """Back from an injury yesterday with some rust left."""
    db.execute(
        "INSERT INTO player_injuries (player_id, league_id, games_remaining,"
        " return_date, rust, rust_days)"
        " VALUES (%s, %s, 5, %s, '{\"speed\": 4.0}'::jsonb, %s)",
        (
            player.id,
            league.id,
            (date.today() - timedelta(days=1)).isoformat(),
            rust_days,
        ),
    )


def _rust_wears_off(db, player):
    db.execute(
        "UPDATE player_injuries SET rust_days = 1 WHERE player_id = %s", (player.id,)
    )


def _rest_rusty(db, gm, on=True):
    db.execute("UPDATE gm_profiles SET rest_rusty = %s WHERE gm_id = %s", (on, gm.id))


def test_rust_wearing_off_is_news_when_resting_rusty(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    _rest_rusty(db_conn, gm)
    rusty = _player_on(db_conn, factory, team, "Rusty")
    still = _player_on(db_conn, factory, team, "Still")
    _back_rusty(db_conn, league, rusty)
    _back_rusty(db_conn, league, still)

    news = InjuryNews(db_conn, league.id)
    _rust_wears_off(db_conn, rusty)
    news.record()

    assert take_injury_news(db_conn, gm.id)["rust_cleared"] == [
        {"name": "Rusty ", "is_pitcher": False}
    ]


def test_no_rust_news_without_rest_rusty(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    _rest_rusty(db_conn, gm, on=False)
    rusty = _player_on(db_conn, factory, team, "Rusty")
    _back_rusty(db_conn, league, rusty)

    news = InjuryNews(db_conn, league.id)
    _rust_wears_off(db_conn, rusty)
    news.record()

    assert take_injury_news(db_conn, gm.id)["rust_cleared"] == []


def test_no_rust_news_when_hurt_again(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    _rest_rusty(db_conn, gm)
    rusty = _player_on(db_conn, factory, team, "Rusty")
    _back_rusty(db_conn, league, rusty)

    news = InjuryNews(db_conn, league.id)
    db_conn.execute(
        "UPDATE player_injuries SET return_date = %s, rust = NULL WHERE player_id = %s",
        ((date.today() + timedelta(days=10)).isoformat(), rusty.id),
    )
    news.record()

    got = take_injury_news(db_conn, gm.id)
    assert got["rust_cleared"] == []
    assert len(got["new_injuries"]) == 1
